import uuid
from datetime import datetime
import enum
from sqlalchemy import Column, String, Integer, DateTime, Enum, Text, ForeignKey, Boolean, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

# Enums
class OrderStatus(str, enum.Enum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"

class PaymentStatus(str, enum.Enum):
    INITIATED = "INITIATED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class PrintStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PRINTING = "PRINTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# Models
class Shop(Base):
    __tablename__ = "shops"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    location = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_phone = Column(String(50), nullable=False)
    file_name = Column(Text, nullable=False)
    file_url = Column(Text, nullable=False)
    copies = Column(Integer, nullable=False, default=1)
    amount = Column(Numeric(10, 2), nullable=False)
    
    order_status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.CREATED)
    
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id", ondelete="SET NULL"))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    payment = relationship("Payment", back_populates="order", uselist=False, cascade="all, delete-orphan")
    print_job = relationship("PrintJob", back_populates="order", uselist=False, cascade="all, delete-orphan")

class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)
    provider_reference = Column(String(255))
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.INITIATED)
    amount = Column(Numeric(10, 2), nullable=False)
    paid_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    order = relationship("Order", back_populates="payment")

class PrintJob(Base):
    __tablename__ = "print_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    
    printer_name = Column(String(100))
    print_status = Column(Enum(PrintStatus), default=PrintStatus.QUEUED)
    retry_count = Column(Integer, default=0)
    printed_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    order = relationship("Order", back_populates="print_job")
