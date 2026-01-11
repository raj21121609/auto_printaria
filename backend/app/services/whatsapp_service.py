import httpx
from app.core.config import get_settings
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

WAS_URL = f"https://graph.facebook.com/v17.0/{settings.PHONE_NUMBER_ID}/messages"

async def send_whatsapp_message(to: str, body: str):
    """
    Sends a text message via WhatsApp Cloud API.
    """
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body}
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(WAS_URL, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Message sent to {to}")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to send message: {e.response.text}")
            # Don't crash app if message fails
            return None
