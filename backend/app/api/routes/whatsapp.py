from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks, Query, Response
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.models import Order, PaymentStatus
from app.services.whatsapp_service import send_whatsapp_message
from app.services.razorpay_service import create_payment_link
import logging
import json

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

@router.get("")
async def verify_whatsapp(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge")
):
    """
    Verification endpoint for WhatsApp Webhook.
    """
    # Debug logging for verification
    expected_token = settings.VERIFY_TOKEN
    logger.info(f"WhatsApp Verification Request: mode={mode}, token={token}, expected={expected_token}")

    if mode == "subscribe" and token == expected_token:
        # Return raw challenge value as text/plain, NOT JSON
        return Response(content=challenge, media_type="text/plain")
    
    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("")
async def handle_whatsapp_message(request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Handle incoming WhatsApp messages and status updates.
    """
    try:
        body = await request.json()
        # Log the full body for debugging (can be removed in production)
        # logger.info(f"Received WhatsApp webhook: {json.dumps(body)}")
        
        entry = body.get("entry", [])
        if not entry:
            return {"status": "ok"}
            
        for changed_entry in entry:
            changes = changed_entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                
                # 1. Handle Status Updates (sent, delivered, read)
                if "statuses" in value:
                    statuses = value["statuses"]
                    for status in statuses:
                        status_id = status.get("id")
                        status_state = status.get("status")
                        recipient_id = status.get("recipient_id")
                        timestamp = status.get("timestamp")
                        
                        logger.info(f"[WhatsApp Status] ID: {status_id} | Recipient: {recipient_id} | Status: {status_state}")
                        # Future: Update message status in DB if needed
                        
                # 2. Handle Incoming Messages
                elif "messages" in value:
                    messages = value["messages"]
                    for message in messages:
                        from_number = message.get("from")
                        msg_type = message.get("type")
                        msg_id = message.get("id")
                        
                        logger.info(f"[WhatsApp Message] From: {from_number} | Type: {msg_type} | ID: {msg_id}")
                        
                        # --- Existing Business Logic (Print Flow) ---
                        # Check for active PENDING order
                        result = await db.execute(
                            select(Order).where(
                                Order.customer_phone == from_number,
                                Order.payment_status == PaymentStatus.PENDING,
                                Order.print_status == "PENDING"
                            ).order_by(Order.created_at.desc())
                        )
                        current_order = result.scalars().first()
                        
        if msg_type == "text":
            text_body = message["text"]["body"].strip().lower()
            logger.info(f"Text Content: {text_body}")
            
            if text_body == "print":
                logger.info(f"Print intent detected from {from_number}")
                
                # Start new order flow or reset existing incomplete one
                if not current_order:
                    # file_url is non-nullable, using placeholder
                    new_order = Order(
                        customer_phone=from_number,
                        file_url="WAITING_FOR_UPLOAD",
                        print_status="WAITING_FILE" 
                    )
                    db.add(new_order)
                    await db.commit()
                    logger.info(f"Created new order {new_order.id} with status WAITING_FILE")
                else:
                    # Update existing pending order to restart flow if needed
                    current_order.print_status = "WAITING_FILE"
                    current_order.file_url = "WAITING_FOR_UPLOAD" # Reset file if they say print again
                    await db.commit()
                    logger.info(f"Updated existing order {current_order.id} to status WAITING_FILE")

                await send_whatsapp_message(from_number, "🖨️ Welcome to Printaria! Please upload the document you want to print.")
            
            else:
                 logger.info(f"Ignored non-print text message: {text_body}")
                 # Strictly ignoring other text for now as per requirements
                 pass

        elif msg_type == "document" or msg_type == "image":
            # Handle file upload (Not implemented yet)
            logger.info(f"Received media {msg_type} from {from_number} but upload handling is skipped.")
            pass

        # Always return 200 OK
        return {"status": "ok"}
            
    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}")
        # Always return ok to prevent retries loop on error, assuming logged
        return {"status": "ok"}
