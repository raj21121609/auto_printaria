from fastapi import APIRouter, Request, Header, HTTPException, Depends
from sqlalchemy.orm import Session
import json
import logging

from app.core.database import get_db
from app.services.payment_service import verify_webhook_signature
from app.models.order import Order
from app.models.payment import Payment
from app.models.print_job import PrintJob
from app.services.queue_service import enqueue_print_job

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Handles Razorpay payment success webhook.
    This is the ONLY source of truth for payment confirmation.
    """

    raw_body = await request.body()

    # 1️⃣ Verify webhook signature
    if not verify_webhook_signature(raw_body, x_razorpay_signature):
        logger.warning("Invalid Razorpay webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = json.loads(raw_body)

    event = payload.get("event")

    # We only care about successful payments
    if event != "payment_link.paid":
        return {"status": "ignored"}

    payment_entity = payload["payload"]["payment"]["entity"]
    payment_link_entity = payload["payload"]["payment_link"]["entity"]

    razorpay_payment_id = payment_entity["id"]
    payment_link_id = payment_link_entity["id"]
    amount_paid = payment_entity["amount"] / 100  # paise → INR

    # 2️⃣ Find payment record
    payment = db.query(Payment).filter(
        Payment.provider_reference == payment_link_id
    ).first()

    if not payment:
        logger.error("Payment record not found for link_id=%s", payment_link_id)
        raise HTTPException(status_code=404, detail="Payment record not found")

    # Idempotency check (VERY IMPORTANT)
    if payment.payment_status == "SUCCESS":
        return {"status": "already processed"}

    # 3️⃣ Update payment
    payment.payment_status = "SUCCESS"
    payment.paid_at = payment_entity["created_at"]

    # 4️⃣ Update order
    order = db.query(Order).filter(Order.id == payment.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.order_status = "PAID"

    # 5️⃣ Create print job (QUEUE MIRROR)
    print_job = PrintJob(
        order_id=order.id,
        shop_id=order.shop_id,
        print_status="QUEUED"
    )

    db.add(print_job)
    db.commit()
    db.refresh(print_job)

    # 6️⃣ Push job to Redis queue
    enqueue_print_job(str(print_job.id))

    logger.info(
        "Payment success → Print job queued | order_id=%s | job_id=%s",
        order.id,
        print_job.id
    )

    return {"status": "success"}
