from fastapi import APIRouter, Request, Depends, BackgroundTasks, HTTPException
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models import Order, PaymentStatus, PrintStatus
from app.services.razorpay_service import verify_webhook_signature
from app.services.whatsapp_service import send_whatsapp_message
from app.services.printer_service import print_document
import logging
import json

router = APIRouter()
logger = logging.getLogger(__name__)

async def process_print_job(order_id: str, db: AsyncSession):
    """
    Background task to handle printing.
    Note: We need a new DB session for background tasks usually, 
    or we pass the data we need. 
    Ideally, we shouldn't share the request-scoped session to background tasks that might outlive it.
    But for simplicity in this flow, passing data is better.
    """
    # Re-instantiate DB session or use a service
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Order).where(Order.id == order_id))
        order = result.scalars().first()
        
        if order and order.payment_status == PaymentStatus.PAID:
            logger.info(f"Starting print job for Order {order_id}")
            order.print_status = PrintStatus.PRINTING
            await session.commit()
            
            success = await print_document(order.file_url)
            
            if success:
                order.print_status = PrintStatus.PRINTED
                await send_whatsapp_message(order.customer_phone, "Payment successful! Your document is printing now.")
            else:
                order.print_status = PrintStatus.FAILED
                await send_whatsapp_message(order.customer_phone, "Payment successful, but printing failed. Please contact support.")
            
            await session.commit()

@router.post("/razorpay-webhook")
async def razorpay_webhook(request: Request, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """
    Handle Razorpay Webhooks.
    """
    try:
        body = await request.body()
        signature = request.headers.get("X-Razorpay-Signature")
        
        if not verify_webhook_signature(body, signature):
            logger.warning("Invalid Razorpay Signature")
            raise HTTPException(status_code=400, detail="Invalid Signature")
            
        event = await request.json()
        event_type = event.get("event")
        payload = event.get("payload", {})
        
        logger.info(f"Received Razorpay Event: {event_type}")
        
        if event_type == "payment_link.paid" or event_type == "payment.captured":
            payment_link = payload.get("payment_link", {}).get("entity", {})
            link_id = payment_link.get("id")
            
            # Find order by payment_link_id
            if link_id:
                result = await db.execute(select(Order).where(Order.razorpay_payment_link_id == link_id))
                order = result.scalars().first()
                
                if order:
                    if order.payment_status != PaymentStatus.PAID:
                        order.payment_status = PaymentStatus.PAID
                        order.razorpay_order_id = payload.get("payment", {}).get("entity", {}).get("order_id")
                        await db.commit()
                        
                        # Trigger Printing Background Task
                        background_tasks.add_task(process_print_job, order.id, db)
                    else:
                        logger.info("Order already paid.")
                else:
                    logger.warning(f"No order found for Payment Link ID: {link_id}")

        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
