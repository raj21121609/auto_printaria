import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Enum, Text
from app.core.database import Base
import enum

class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"

class PrintStatus(str, enum.Enum):
    PENDING = "PENDING"
    PRINTING = "PRINTING"
    PRINTED = "PRINTED"
    FAILED = "FAILED"

class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_phone = Column(String, index=True, nullable=False)
    file_url = Column(Text, nullable=False)
    copies = Column(Integer, default=1)
    
    razorpay_payment_link_id = Column(String, unique=True, index=True, nullable=True)
    razorpay_order_id = Column(String, index=True, nullable=True) # Optional link to Razorpay order if needed
    
    payment_status = Column(String, default=PaymentStatus.PENDING.value)
    print_status = Column(String, default=PrintStatus.PENDING.value)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
