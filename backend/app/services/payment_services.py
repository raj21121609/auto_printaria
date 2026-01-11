from sqlalchemy.orm import Session
from app.models.order import Order
from app.models.print_job import PrintJob
from app.services.queue_service import enqueue_print_job

def handle_payment_success(order_id, db: Session):
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise Exception("Order not found")

    # 1️⃣ Update order (business truth)
    order.order_status = "PAID"

    # 2️⃣ Create print job (queue mirror)
    job = PrintJob(
        order_id=order.id,
        shop_id=order.shop_id,
        print_status="QUEUED"
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # 3️⃣ Push job ID to Redis queue
    enqueue_print_job(str(job.id))
