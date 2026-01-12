"""
Order Service for AMP K

Handles order creation, price calculation, and lifecycle management.
"""

import uuid
import hashlib
import os
from datetime import datetime
from typing import Optional, Tuple
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.models import (
    Order, OrderStatus, Payment, PaymentStatus, 
    PrintJob, PrintStatus, PrintType, Shop, UserSession
)
from app.core.config import get_settings
from app.services.razorpay_service import create_payment_link
import logging

settings = get_settings()
logger = logging.getLogger(__name__)


# =============================================================================
# PRICE CALCULATION
# =============================================================================

def calculate_price(
    print_type: PrintType,
    copies: int,
    page_count: int = 1,
    price_bw: float = None,
    price_color: float = None
) -> Decimal:
    """
    Calculate order total based on print type, copies, and page count.
    
    Pricing logic:
    - BW: page_count × copies × price_per_page_bw
    - COLOR: page_count × copies × price_per_page_color
    - BOTH: (BW price + COLOR price) for the same document
    
    Args:
        print_type: COLOR, BW, or BOTH
        copies: Number of copies
        page_count: Number of pages in document
        price_bw: Override B&W price per page
        price_color: Override color price per page
        
    Returns:
        Total price as Decimal
    """
    price_bw = price_bw or settings.PRICE_PER_PAGE_BW
    price_color = price_color or settings.PRICE_PER_PAGE_COLOR
    
    if print_type == PrintType.BW:
        total = page_count * copies * price_bw
    elif print_type == PrintType.COLOR:
        total = page_count * copies * price_color
    elif print_type == PrintType.BOTH:
        # BOTH means one set of color + one set of BW
        total = page_count * copies * (price_bw + price_color)
    else:
        total = 0
    
    return Decimal(str(round(total, 2)))


# =============================================================================
# ORDER MANAGEMENT
# =============================================================================

async def create_draft_order(
    db: AsyncSession,
    customer_phone: str,
    shop_id: uuid.UUID = None
) -> Order:
    """
    Create a new draft order for a customer.
    
    Args:
        db: Database session
        customer_phone: Customer's WhatsApp number
        shop_id: Optional shop ID (uses default if not provided)
        
    Returns:
        Created Order object
    """
    # Use default shop if not specified
    if not shop_id and settings.DEFAULT_SHOP_ID:
        shop_id = uuid.UUID(settings.DEFAULT_SHOP_ID)
    
    order = Order(
        customer_phone=customer_phone,
        order_status=OrderStatus.DRAFT,
        shop_id=shop_id,
        amount=Decimal("0.00")
    )
    
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    logger.info(f"Created draft order {order.id} for {customer_phone}")
    return order


async def update_order_file(
    db: AsyncSession,
    order: Order,
    file_name: str,
    file_url: str,
    file_media_id: str = None,
    page_count: int = 1
) -> Order:
    """
    Update order with file information.
    """
    order.file_name = file_name
    order.file_url = file_url
    order.file_media_id = file_media_id
    order.page_count = page_count
    
    await db.commit()
    await db.refresh(order)
    
    logger.info(f"Updated order {order.id} with file: {file_name}")
    return order


async def update_order_print_config(
    db: AsyncSession,
    order: Order,
    print_type: PrintType,
    copies: int
) -> Order:
    """
    Update order with print configuration and calculate price.
    """
    order.print_type = print_type
    order.copies = copies
    
    # Calculate price
    order.amount = calculate_price(
        print_type=print_type,
        copies=copies,
        page_count=order.page_count or 1
    )
    
    await db.commit()
    await db.refresh(order)
    
    logger.info(f"Updated order {order.id}: {print_type.value}, {copies} copies, ₹{order.amount}")
    return order


async def finalize_order_with_payment_link(
    db: AsyncSession,
    order: Order
) -> Tuple[Order, str]:
    """
    Generate Razorpay payment link and finalize order.
    
    Returns:
        Tuple of (updated order, payment_link_url)
    """
    if order.order_status != OrderStatus.DRAFT:
        raise ValueError(f"Order {order.id} is not in DRAFT status")
    
    if not order.amount or order.amount <= 0:
        raise ValueError(f"Order {order.id} has invalid amount")
    
    # Generate payment link with order ID as reference
    reference_id = str(order.id)
    description = f"Print Order: {order.file_name or 'Document'}"
    
    payment_url, payment_link_id = create_payment_link(
        amount=float(order.amount),
        reference_id=reference_id,
        description=description,
        customer_phone=order.customer_phone
    )
    
    # Update order with payment link info
    order.razorpay_payment_link_id = payment_link_id
    order.razorpay_payment_link_url = payment_url
    order.order_status = OrderStatus.PAYMENT_PENDING
    
    # Create payment record
    payment = Payment(
        order_id=order.id,
        payment_link_id=payment_link_id,
        amount=order.amount,
        payment_status=PaymentStatus.INITIATED
    )
    db.add(payment)
    
    await db.commit()
    await db.refresh(order)
    
    logger.info(f"Order {order.id} finalized with payment link: {payment_link_id}")
    return order, payment_url


async def confirm_payment(
    db: AsyncSession,
    payment_link_id: str,
    razorpay_payment_id: str,
    amount_paid: Decimal
) -> Optional[Order]:
    """
    Confirm payment and create print job.
    
    This is called from the Razorpay webhook handler.
    
    Args:
        db: Database session
        payment_link_id: Razorpay payment link ID (plink_xxx)
        razorpay_payment_id: Razorpay payment ID (pay_xxx)
        amount_paid: Amount paid in INR
        
    Returns:
        Updated Order if successful, None if already processed or not found
    """
    # Find order by payment link ID
    result = await db.execute(
        select(Order).where(Order.razorpay_payment_link_id == payment_link_id)
    )
    order = result.scalars().first()
    
    if not order:
        logger.error(f"Order not found for payment_link_id: {payment_link_id}")
        return None
    
    # Idempotency check - already paid
    if order.order_status == OrderStatus.PAID:
        logger.info(f"Order {order.id} already paid, skipping")
        return order
    
    # Update payment record
    result = await db.execute(
        select(Payment).where(Payment.order_id == order.id)
    )
    payment = result.scalars().first()
    
    if payment:
        payment.payment_status = PaymentStatus.SUCCESS
        payment.provider_reference = razorpay_payment_id
        payment.paid_at = datetime.utcnow()
    
    # Update order status
    order.order_status = OrderStatus.PAID
    
    # Create print job
    print_job = PrintJob(
        order_id=order.id,
        shop_id=order.shop_id,
        print_status=PrintStatus.QUEUED
    )
    db.add(print_job)
    
    await db.commit()
    await db.refresh(order)
    await db.refresh(print_job)
    
    logger.info(f"Payment confirmed for order {order.id}, print job {print_job.id} created")
    return order


async def get_order_by_id(db: AsyncSession, order_id: uuid.UUID) -> Optional[Order]:
    """Get order by ID."""
    result = await db.execute(select(Order).where(Order.id == order_id))
    return result.scalars().first()


async def get_order_by_payment_link(db: AsyncSession, payment_link_id: str) -> Optional[Order]:
    """Get order by Razorpay payment link ID."""
    result = await db.execute(
        select(Order).where(Order.razorpay_payment_link_id == payment_link_id)
    )
    return result.scalars().first()


# =============================================================================
# FILE HANDLING
# =============================================================================

async def save_uploaded_file(
    file_content: bytes,
    filename: str,
    customer_phone: str
) -> Tuple[str, str]:
    """
    Save uploaded file to local storage.
    
    Args:
        file_content: File bytes
        filename: Original filename
        customer_phone: Customer phone for organizing files
        
    Returns:
        Tuple of (file_path, file_url)
    """
    # Create directory structure
    upload_dir = os.path.join(settings.FILE_STORAGE_PATH, customer_phone.replace("+", "").replace(":", "_"))
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate unique filename
    file_hash = hashlib.sha256(file_content).hexdigest()[:16]
    safe_filename = f"{file_hash}_{filename}"
    file_path = os.path.join(upload_dir, safe_filename)
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(file_content)
    
    # Generate URL for file access
    # This assumes a /files endpoint serves the uploads directory
    relative_path = os.path.relpath(file_path, settings.FILE_STORAGE_PATH)
    file_url = f"{settings.BACKEND_PUBLIC_URL}/files/{relative_path.replace(os.sep, '/')}"
    
    logger.info(f"Saved file {filename} to {file_path}")
    return file_path, file_url


def compute_file_hash(content: bytes) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(content).hexdigest()
