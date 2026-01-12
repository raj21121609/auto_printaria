from fastapi import APIRouter, Form, Response
import logging
from twilio.twiml.messaging_response import MessagingResponse

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("")
async def handle_twilio_webhook(
    From: str = Form(...),
    Body: str = Form(...)
):
    """
    Handle Twilio WhatsApp Webhook.
    POST /webhook/twilio
    """
    try:
        logger.info(f"Twilio Message from {From}: {Body}")
        
        # Create TwiML Response
        resp = MessagingResponse()
        resp.message("Hello from Twilio bot!")
        
        # Return XML Response
        return Response(content=str(resp), media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error handling Twilio webhook: {e}")
        # Return empty TwiML to avoid errors on Twilio side indicating failure
        resp = MessagingResponse()
        return Response(content=str(resp), media_type="application/xml")
