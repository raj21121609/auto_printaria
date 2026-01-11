import razorpay
from app.core.config import get_settings
from fastapi import HTTPException
import hmac
import hashlib
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

# Initialize Razorpay Client
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def create_payment_link(amount: float, reference_id: str, description: str = "Printaria Order") -> str:
    """
    Creates a Razorpay Payment Link.
    Amount should be in currency subunits (e.g., paise).
    """
    try:
        data = {
            "amount": int(amount * 100),  # Convert to paise
            "currency": "INR",
            "accept_partial": False,
            "reference_id": reference_id,
            "description": description,
            "customer": {
                "contact": "+910000000000", # Ideally get from user
                "email": "user@example.com"
            },
            "notify": {
                "sms": True,
                "email": True
            },
            "reminder_enable": True,
            "callback_url": "https://printaria.com/callback", # Placeholder
            "callback_method": "get"
        }
        payment_link = client.payment_link.create(data)
        return payment_link['short_url'], payment_link['id']
    except Exception as e:
        logger.error(f"Error creating Razorpay link: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment link")

def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """
    Verifies the Razorpay webhook signature using HMAC SHA256.
    """
    try:
        # Client utility method is preferred if available/working, 
        # but manual HMAC is often more robust for debugging.
        # client.utility.verify_webhook_signature(body_str, signature, secret)
        
        secret = settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8')
        generated_signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(generated_signature, signature)
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False
