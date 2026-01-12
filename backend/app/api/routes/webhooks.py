"""
Webhook Handlers for AMP K

Handles:
- Razorpay payment webhooks (source of truth for payment confirmation)
- Payment success callback
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from decimal import Decimal
from datetime import datetime
import hashlib
import logging
import json

from app.core.database import get_db
from app.models import (
    Order, Payment, PrintJob, PaymentStatus, OrderStatus, 
    PrintStatus, WebhookLog, UserSession, ConversationState
)
from app.services.razorpay_service import verify_webhook_signature
from app.services.queue_service import enqueue_print_job
from app.services import twilio_service, session_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/razorpay-webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Handle Razorpay Webhooks.
    
    This is the ONLY source of truth for payment confirmation.
    
    Events handled:
    - payment_link.paid: Payment link has been paid
    - payment.captured: Payment has been captured
    
    Security:
    - HMAC signature verification
    - Idempotent processing (prevents duplicate handling)
    """
    try:
        body = await request.body()
        signature = request.headers.get("X-Razorpay-Signature")
        
        # 1. Verify webhook signature
        if not verify_webhook_signature(body, signature):
            logger.warning("Invalid Razorpay Signature")
            raise HTTPException(status_code=400, detail="Invalid Signature")
        
        event = json.loads(body)
        event_type = event.get("event")
        payload = event.get("payload", {})
        
        # Generate event ID for idempotency
        # Razorpay doesn't always provide a unique event ID, so we hash the payload
        event_id = event.get("event_id") or hashlib.sha256(body).hexdigest()[:32]
        
        logger.info(f"Received Razorpay Event: {event_type}, ID: {event_id}")
        
        # 2. Check idempotency - have we processed this event?
        existing = await db.execute(
            select(WebhookLog).where(WebhookLog.event_id == event_id)
        )
        if existing.scalars().first():
            logger.info(f"Event {event_id} already processed, skipping")
            return {"status": "already_processed"}
        
        # 3. Process based on event type
        result = {"status": "ignored"}
        
        if event_type == "payment_link.paid":
            result = await handle_payment_link_paid(db, payload)
        elif event_type == "payment.captured":
            result = await handle_payment_captured(db, payload)
        
        # 4. Log successful processing
        webhook_log = WebhookLog(
            event_id=event_id,
            event_type=event_type,
            provider="razorpay",
            payload_hash=hashlib.sha256(body).hexdigest()
        )
        db.add(webhook_log)
        await db.commit()
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Razorpay webhook: {e}", exc_info=True)
        # Return 200 to prevent Razorpay from retrying on logic errors
        # For genuine server errors, you might want 500
        return {"status": "error", "detail": str(e)}


async def handle_payment_link_paid(db: AsyncSession, payload: dict) -> dict:
    """
    Handle payment_link.paid event.
    
    This is the primary event we receive when using Razorpay Payment Links.
    
    Payload structure:
    {
        "payment_link": {"entity": {...}},
        "payment": {"entity": {...}}
    }
    """
    try:
        payment_link_entity = payload.get("payment_link", {}).get("entity", {})
        payment_entity = payload.get("payment", {}).get("entity", {})
        
        payment_link_id = payment_link_entity.get("id")  # plink_xxx
        razorpay_payment_id = payment_entity.get("id")   # pay_xxx
        amount_paid = Decimal(str(payment_entity.get("amount", 0))) / 100  # paise -> INR
        reference_id = payment_link_entity.get("reference_id")  # Our order ID
        
        logger.info(f"Payment Link Paid: {payment_link_id}, ref: {reference_id}, amount: ₹{amount_paid}")
        
        if not payment_link_id:
            logger.error("No payment_link_id in payload")
            return {"status": "error", "detail": "missing_payment_link_id"}
        
        # Find order by payment link ID
        result = await db.execute(
            select(Order).where(Order.razorpay_payment_link_id == payment_link_id)
        )
        order = result.scalars().first()
        
        if not order:
            # Fallback: try reference_id which should be order UUID
            if reference_id:
                try:
                    import uuid
                    order_uuid = uuid.UUID(reference_id)
                    result = await db.execute(
                        select(Order).where(Order.id == order_uuid)
                    )
                    order = result.scalars().first()
                except ValueError:
                    pass
        
        if not order:
            logger.error(f"Order not found for payment_link_id: {payment_link_id}")
            return {"status": "error", "detail": "order_not_found"}
        
        # Idempotency check - order already paid
        if order.order_status == OrderStatus.PAID:
            logger.info(f"Order {order.id} already paid")
            return {"status": "already_paid"}
        
        # === BEGIN TRANSACTION ===
        
        # 1. Update payment record
        result = await db.execute(
            select(Payment).where(Payment.order_id == order.id)
        )
        payment = result.scalars().first()
        
        if payment:
            payment.payment_status = PaymentStatus.SUCCESS
            payment.provider_reference = razorpay_payment_id
            payment.paid_at = datetime.utcnow()
        else:
            # Create payment record if missing
            payment = Payment(
                order_id=order.id,
                payment_link_id=payment_link_id,
                provider_reference=razorpay_payment_id,
                amount=amount_paid,
                payment_status=PaymentStatus.SUCCESS,
                paid_at=datetime.utcnow()
            )
            db.add(payment)
        
        # 2. Update order status
        order.order_status = OrderStatus.PAID
        
        # 3. Create print job
        print_job = PrintJob(
            order_id=order.id,
            shop_id=order.shop_id,
            print_status=PrintStatus.QUEUED
        )
        db.add(print_job)
        
        # Commit all changes atomically
        await db.commit()
        await db.refresh(print_job)
        
        # === END TRANSACTION ===
        
        # 4. Enqueue print job to Redis
        enqueue_print_job(str(print_job.id))
        
        logger.info(f"Order {order.id} paid. Print job {print_job.id} queued.")
        
        # 5. Send WhatsApp confirmation to customer
        await send_payment_confirmation(db, order)
        
        return {"status": "success", "order_id": str(order.id), "print_job_id": str(print_job.id)}
        
    except Exception as e:
        logger.error(f"Error handling payment_link.paid: {e}", exc_info=True)
        await db.rollback()
        raise


async def handle_payment_captured(db: AsyncSession, payload: dict) -> dict:
    """
    Handle payment.captured event.
    
    This is a backup/alternative event type.
    For Payment Links, payment_link.paid is more reliable.
    """
    try:
        payment_entity = payload.get("payment", {}).get("entity", {})
        
        razorpay_payment_id = payment_entity.get("id")
        notes = payment_entity.get("notes", {})
        order_id_str = notes.get("order_id")
        
        if not order_id_str:
            logger.info("No order_id in notes, skipping payment.captured")
            return {"status": "ignored"}
        
        logger.info(f"Payment Captured: {razorpay_payment_id}, order: {order_id_str}")
        
        # Similar logic to handle_payment_link_paid...
        # This is a fallback, so just log for now
        return {"status": "noted"}
        
    except Exception as e:
        logger.error(f"Error handling payment.captured: {e}")
        return {"status": "error"}


async def send_payment_confirmation(db: AsyncSession, order: Order):
    """
    Send WhatsApp notification to customer after payment success.
    Also updates conversation state.
    """
    try:
        # Send confirmation message
        await twilio_service.send_whatsapp_message(
            to=order.customer_phone,
            body=twilio_service.msg_payment_success(str(order.id))
        )
        
        # Clear user session
        session = await session_service.get_session_by_phone(db, order.customer_phone)
        if session:
            await session_service.clear_session(db, session)
        
        logger.info(f"Payment confirmation sent to {order.customer_phone}")
        
    except Exception as e:
        logger.error(f"Failed to send payment confirmation: {e}")


@router.get("/razorpay-callback")
async def razorpay_callback(
    razorpay_payment_id: str = Query(None),
    razorpay_payment_link_id: str = Query(None),
    razorpay_payment_link_reference_id: str = Query(None),
    razorpay_payment_link_status: str = Query(None),
    razorpay_signature: str = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Razorpay Payment Link callback URL.
    
    This is called when user completes payment and is redirected back.
    Not the source of truth - just for UI redirect purposes.
    The actual confirmation happens via webhook.
    
    Query params:
    - razorpay_payment_id
    - razorpay_payment_link_id
    - razorpay_payment_link_reference_id
    - razorpay_payment_link_status
    - razorpay_signature
    """
    logger.info(f"Payment callback: link={razorpay_payment_link_id}, status={razorpay_payment_link_status}")
    
    # Simple redirect or confirmation page
    # In production, redirect to a thank you page
    if razorpay_payment_link_status == "paid":
        return {
            "status": "success",
            "message": "Payment successful! You will receive a WhatsApp confirmation shortly."
        }
    else:
        return {
            "status": "pending",
            "message": "Payment status: " + (razorpay_payment_link_status or "unknown")
        }
