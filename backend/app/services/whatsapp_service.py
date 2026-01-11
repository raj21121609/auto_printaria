import httpx
from app.core.config import get_settings
import logging
import json

settings = get_settings()
logger = logging.getLogger(__name__)

GUPSHUP_URL = "https://api.gupshup.io/wa/api/v1/msg"

async def send_whatsapp_message(to: str, body: str):
    """
    Sends a text message via Gupshup WhatsApp API.
    """
    headers = {
        "apikey": settings.GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # Gupshup expects 'message' as a JSON string for structured content
    message_payload = json.dumps({
        "type": "text",
        "text": body
    })
    
    data = {
        "channel": "whatsapp",
        "source": settings.GUPSHUP_WHATSAPP_NUMBER,
        "destination": to,
        "message": message_payload,
        "src.name": settings.GUPSHUP_APP_NAME 
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(GUPSHUP_URL, data=data, headers=headers)
            response.raise_for_status()
            logger.info(f"Message sent to {to} via Gupshup")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to send message: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
