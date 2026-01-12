"""
Twilio WhatsApp Service for AMP K

Handles sending WhatsApp messages via Twilio API.
Supports text messages and interactive button messages.

Note: Twilio WhatsApp Sandbox has limitations on button messages.
For production, use approved templates.
"""

from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from app.core.config import get_settings
import logging
import httpx
from typing import Optional, List
from urllib.parse import urljoin

settings = get_settings()
logger = logging.getLogger(__name__)

# Initialize Twilio client
_client = None


def get_twilio_client() -> Optional[Client]:
    """Get or create Twilio client singleton."""
    global _client
    if _client is None and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
        _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client


async def send_whatsapp_message(to: str, body: str) -> bool:
    """
    Send a simple text message via Twilio WhatsApp.
    
    Args:
        to: Recipient phone number (e.g., "whatsapp:+919876543210")
        body: Message text
        
    Returns:
        True if sent successfully, False otherwise
    """
    try:
        client = get_twilio_client()
        if not client:
            logger.error("Twilio client not configured")
            return False
        
        # Ensure proper format
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"
        
        from_number = settings.TWILIO_WHATSAPP_NUMBER
        if not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"
        
        message = client.messages.create(
            body=body,
            from_=from_number,
            to=to
        )
        
        logger.info(f"Sent WhatsApp message to {to}: {message.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {to}: {e}")
        return False


async def send_button_message(to: str, body: str, buttons: List[dict]) -> bool:
    """
    Send an interactive button message.
    
    Note: Twilio Sandbox does not support interactive messages.
    In sandbox mode, this falls back to numbered options.
    
    For production with approved templates, use the Twilio Content API.
    
    Args:
        to: Recipient phone number
        body: Message body text
        buttons: List of button dicts with 'id' and 'title' keys
                 e.g., [{"id": "color", "title": "Color Xerox"}, ...]
    
    Returns:
        True if sent successfully
    """
    # Sandbox fallback: Send numbered options
    # Users reply with the number to select
    options_text = "\n".join([
        f"{i+1}. {btn['title']}" 
        for i, btn in enumerate(buttons)
    ])
    
    full_message = f"{body}\n\n{options_text}\n\n_Reply with the number to select._"
    
    return await send_whatsapp_message(to, full_message)


async def download_media_file(media_url: str, media_sid: str) -> Optional[tuple]:
    """
    Download a media file from Twilio.
    
    Twilio media URLs require authentication.
    
    Args:
        media_url: The Twilio media URL
        media_sid: The MediaSid for logging
        
    Returns:
        Tuple of (file_bytes, content_type, filename) or None on failure
    """
    try:
        # Twilio media URLs require basic auth
        auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                media_url,
                auth=auth,
                follow_redirects=True,
                timeout=60.0
            )
            response.raise_for_status()
            
            content_type = response.headers.get("content-type", "application/octet-stream")
            
            # Try to get filename from content-disposition or generate one
            content_disp = response.headers.get("content-disposition", "")
            filename = None
            if "filename=" in content_disp:
                filename = content_disp.split("filename=")[-1].strip('"\'')
            
            if not filename:
                # Generate filename from media_sid and content type
                ext = _get_extension_from_content_type(content_type)
                filename = f"{media_sid}{ext}"
            
            logger.info(f"Downloaded media {media_sid}: {len(response.content)} bytes, {content_type}")
            return (response.content, content_type, filename)
            
    except Exception as e:
        logger.error(f"Failed to download media {media_sid}: {e}")
        return None


def _get_extension_from_content_type(content_type: str) -> str:
    """Map content type to file extension."""
    mapping = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-powerpoint": ".ppt",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "text/plain": ".txt",
    }
    return mapping.get(content_type.split(";")[0].strip(), ".bin")


def create_twiml_response(message: str = None) -> MessagingResponse:
    """
    Create a TwiML MessagingResponse.
    
    Args:
        message: Optional text message to include
        
    Returns:
        MessagingResponse object
    """
    resp = MessagingResponse()
    if message:
        resp.message(message)
    return resp


# =============================================================================
# MESSAGE TEMPLATES
# =============================================================================

def msg_welcome() -> str:
    return (
        "🖨️ *Welcome to AMP K Print Service!*\n\n"
        "Send me a document (PDF, Word, Image) to get started.\n\n"
        "_Supported formats: PDF, DOC, DOCX, JPG, PNG_"
    )


def msg_file_received(filename: str) -> str:
    return (
        f"✅ *File Received:* {filename}\n\n"
        "Select print type:\n\n"
        "1. 🎨 *Color Xerox*\n"
        "2. ⬛ *Black & White*\n"
        "3. 🔀 *Both (Color + B&W)*\n\n"
        "_Reply with 1, 2, or 3_"
    )


def msg_print_type_selected(print_type: str) -> str:
    type_display = {
        "COLOR": "🎨 Color Xerox",
        "BW": "⬛ Black & White",
        "BOTH": "🔀 Both (Color + B&W)"
    }
    return (
        f"✅ *Print Type:* {type_display.get(print_type, print_type)}\n\n"
        "How many copies do you need?\n\n"
        "_Reply with a number (1-100)_"
    )


def msg_order_summary(filename: str, print_type: str, copies: int, amount: float) -> str:
    type_display = {
        "COLOR": "🎨 Color",
        "BW": "⬛ Black & White",
        "BOTH": "🔀 Both"
    }
    return (
        "📋 *ORDER SUMMARY*\n"
        "━━━━━━━━━━━━━━━━\n"
        f"📄 File: {filename}\n"
        f"🖨️ Type: {type_display.get(print_type, print_type)}\n"
        f"📑 Copies: {copies}\n"
        f"💰 Total: ₹{amount:.2f}\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "Click the payment link below to complete your order."
    )


def msg_payment_link(payment_url: str) -> str:
    return f"💳 *Pay Now:* {payment_url}"


def msg_payment_success(order_id: str) -> str:
    return (
        "✅ *PAYMENT SUCCESSFUL!*\n\n"
        f"Order ID: {order_id[:8]}...\n\n"
        "Your document has been queued for printing.\n"
        "We'll notify you when it's ready! 🖨️"
    )


def msg_print_complete(order_id: str) -> str:
    return (
        "🎉 *PRINT COMPLETE!*\n\n"
        f"Order ID: {order_id[:8]}...\n\n"
        "Your document is ready for pickup.\n"
        "Thank you for using AMP K! 🙏"
    )


def msg_print_failed(order_id: str) -> str:
    return (
        "❌ *PRINT FAILED*\n\n"
        f"Order ID: {order_id[:8]}...\n\n"
        "There was an issue printing your document.\n"
        "Please contact the shop for assistance."
    )


def msg_invalid_input() -> str:
    return "❌ Invalid input. Please try again."


def msg_invalid_copies() -> str:
    return "❌ Please enter a valid number between 1 and 100."


def msg_session_expired() -> str:
    return (
        "⏰ Your session has expired.\n\n"
        "Please send a document to start a new order."
    )
