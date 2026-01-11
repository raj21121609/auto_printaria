from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.models import Order, Payment, PrintJob, PaymentStatus, OrderStatus, PrintStatus
from app.services.razorpay_service import verify_webhook_signature
from app.services.queue_service import enqueue_print_job
import logging
import json
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/razorpay-webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
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
        
        if event_type == "payment.captured":
            payment_entity = payload.get("payment", {}).get("entity", {})
            order_id = payment_entity.get("notes", {}).get("order_id") # Assuming we send order_id in notes
            razorpay_payment_id = payment_entity.get("id")
            amount = payment_entity.get("amount") # In paise

             # If order_id not in notes (e.g. payment links), fallback logic might be needed 
             # For this strict implementation, we assume strict linkage via notes or strict payment link id mapping
             # Logic below assumes we find the order via some identifier. 
             # Let's assume the payment is linked to an order via 'notes.order_id' or we lookup payment link.
            
            # Simple fallback lookup if order_id is missing from notes:
            # If you use payment links, Razorpay sends 'payment_link' object or 'order_id' might be null.
            # But let's assume we can resolve the order.

            if not order_id:
                # Try to find via payment link if implemented
                logger.warning("No order_id in notes, skipping for now.")
                return {"status": "ignored"}

            # Fetch Order
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalars().first()
            
            if order:
                if order.order_status != OrderStatus.PAID:
                    # 1. Update Payment Record
                    # Check if payment record exists
                    p_result = await db.execute(select(Payment).where(Payment.order_id == order.id))
                    payment_record = p_result.scalars().first()
                    
                    if not payment_record:
                        payment_record = Payment(
                            order_id=order.id, 
                            amount=amount/100, 
                            payment_status=PaymentStatus.INITIATED
                        )
                        db.add(payment_record)
                    
                    payment_record.payment_status = PaymentStatus.SUCCESS
                    payment_record.provider_reference = razorpay_payment_id
                    payment_record.paid_at = datetime.utcnow()
                    
                    # 2. Update Order Status
                    order.order_status = OrderStatus.PAID
                    
                    # 3. Create Print Job
                    print_job = PrintJob(
                        order_id=order.id,
                        shop_id=order.shop_id,
                        print_status=PrintStatus.QUEUED
                    )
                    db.add(print_job)
                    
                    await db.commit()
                    await db.refresh(print_job)
                    
                    # 4. Enqueue to Redis
                    enqueue_print_job(str(print_job.id))
                    
                    logger.info(f"Order {order.id} paid. queue job {print_job.id}")
                else:
                    logger.info(f"Order {order.id} already processed.")
            else:
                 logger.warning(f"Order {order_id} not found.")

        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        # Return 200 to prevent Razorpay from retrying indefinitely on logic errors, 
        # but in production you might want 500 for genuine server errors.
        return {"status": "error", "detail": str(e)}
