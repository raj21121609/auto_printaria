"""
Razorpay Service for AMP K

Handles payment link creation and webhook signature verification.
"""

import razorpay
from app.core.config import get_settings
from fastapi import HTTPException
import hmac
import hashlib
import logging
from typing import Tuple

settings = get_settings()
logger = logging.getLogger(__name__)

# Initialize Razorpay Client
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_payment_link(
    amount: float,
    reference_id: str,
    description: str = "AMP K Print Order",
    customer_phone: str = None
) -> Tuple[str, str]:
    """
    Creates a Razorpay Payment Link.
    
    Args:
        amount: Amount in INR (will be converted to paise)
        reference_id: Unique reference ID (typically order UUID)
        description: Payment description
        customer_phone: Customer's phone number for notifications
        
    Returns:
        Tuple of (payment_url, payment_link_id)
    """
    try:
        # Clean phone number
        if customer_phone:
            # Remove whatsapp: prefix and non-numeric chars except +
            phone = customer_phone.replace("whatsapp:", "")
            # Ensure starts with +91 for India
            if not phone.startswith("+"):
                phone = f"+91{phone.lstrip('0')}"
        else:
            phone = "+910000000000"
        
        data = {
            "amount": int(amount * 100),  # Convert to paise
            "currency": "INR",
            "accept_partial": False,
            "reference_id": reference_id,
            "description": description,
            "customer": {
                "contact": phone,
            },
            "notify": {
                "sms": True,
                "email": False,
                "whatsapp": False  # We handle WhatsApp ourselves
            },
            "reminder_enable": True,
            "callback_url": f"{settings.BACKEND_PUBLIC_URL}/api/webhooks/razorpay-callback",
            "callback_method": "get",
            "expire_by": int(__import__('time').time()) + (24 * 60 * 60),  # 24 hours
            "notes": {
                "order_id": reference_id,
                "source": "amp_k_whatsapp"
            }
        }
        
        payment_link = client.payment_link.create(data)
        
        logger.info(f"Created payment link {payment_link['id']} for reference {reference_id}")
        return payment_link['short_url'], payment_link['id']
        
    except Exception as e:
        logger.error(f"Error creating Razorpay link: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment link")


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """
    Verifies the Razorpay webhook signature using HMAC SHA256.
    
    Args:
        body: Raw request body bytes
        signature: X-Razorpay-Signature header value
        
    Returns:
        True if signature is valid, False otherwise
    """
    if not signature:
        logger.warning("No signature provided")
        return False
        
    try:
        secret = settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8')
        generated_signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
        
        is_valid = hmac.compare_digest(generated_signature, signature)
        
        if not is_valid:
            logger.warning(f"Signature mismatch. Expected: {generated_signature[:20]}..., Got: {signature[:20]}...")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False


def get_payment_link_status(payment_link_id: str) -> dict:
    """
    Fetch payment link status from Razorpay.
    
    Args:
        payment_link_id: Razorpay payment link ID (plink_xxx)
        
    Returns:
        Payment link details dict
    """
    try:
        return client.payment_link.fetch(payment_link_id)
    except Exception as e:
        logger.error(f"Failed to fetch payment link {payment_link_id}: {e}")
        return None
