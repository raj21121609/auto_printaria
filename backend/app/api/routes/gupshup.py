from fastapi import APIRouter, Request, Depends, BackgroundTasks
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models import Order, OrderStatus, PaymentStatus, PrintStatus
from app.services.whatsapp_service import send_whatsapp_message
import logging
import json

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("")
async def handle_gupshup_webhook(request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Handle incoming Gupshup messages.
    POST /webhooks/gupshup
    """
    try:
        # 1. Parse Payload
        payload = await request.json()
        logger.info(f"Received Gupshup webhook: {json.dumps(payload)}")
        
        # Gupshup usually sends 'payload' or 'type' at root.
        # Structure varies by version but generic handling:
        # Check if it is a 'message' event
        if payload.get("type") == "message":
            msg_payload = payload.get("payload", {})
            
            # Extract basic info
            # 'source' is usually the sender phone number in Gupshup
            from_number = msg_payload.get("source")
            msg_type = msg_payload.get("type") # text, image, file, etc.
            
            if not from_number:
                # Meta passthrough might be different, but let's handle standard Gupshup
                return {"status": "ok"}
            
            # 2. Handle Text Messages
            if msg_type == "text":
                text_body = msg_payload.get("payload", {}).get("text", "").strip().lower()
                logger.info(f"Text from {from_number}: {text_body}")
                
                if text_body in ["hi", "hello"]:
                    msg = "Hi 👋 Welcome to Printaria. Please upload the document you want to print."
                    await send_whatsapp_message(from_number, msg)
                else:
                    msg = "Please upload a file (PDF/Image) to continue."
                    await send_whatsapp_message(from_number, msg)
            
            # 3. Handle File Messages
            elif msg_type in ["image", "file", "document", "ptype"]:
                 # 'ptype' is sometimes used by Gupshup for files if not standardized
                 logger.info(f"Received media {msg_type} from {from_number}")
                 
                 # Extract file details if possible (for logs)
                 file_url = msg_payload.get("payload", {}).get("url")
                 file_name = msg_payload.get("payload", {}).get("name")
                 logger.info(f"File: {file_name} URL: {file_url}")
                 
                 msg = "📄 File received successfully. How many copies do you want?"
                 await send_whatsapp_message(from_number, msg)

        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error handling Gupshup webhook: {e}")
        return {"status": "ok"}
