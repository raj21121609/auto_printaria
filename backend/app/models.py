import uuid
from datetime import datetime
import enum
from sqlalchemy import Column, String, Integer, DateTime, Enum, Text, ForeignKey, Boolean, Numeric, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


# =============================================================================
# ENUMS
# =============================================================================

class OrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"                    # Order being built via conversation
    PAYMENT_PENDING = "PAYMENT_PENDING" # Awaiting payment
    PAID = "PAID"                      # Payment confirmed
    CANCELLED = "CANCELLED"            # Order cancelled

class PaymentStatus(str, enum.Enum):
    INITIATED = "INITIATED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class PrintStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PRINTING = "PRINTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class PrintType(str, enum.Enum):
    COLOR = "COLOR"
    BW = "BW"
    BOTH = "BOTH"

class ConversationState(str, enum.Enum):
    """State machine for WhatsApp conversation flow"""
    IDLE = "IDLE"                           # Waiting for user to start
    AWAITING_FILE = "AWAITING_FILE"         # Waiting for file upload
    AWAITING_PRINT_TYPE = "AWAITING_PRINT_TYPE"  # Waiting for print type selection
    AWAITING_COPIES = "AWAITING_COPIES"     # Waiting for number of copies
    AWAITING_PAYMENT = "AWAITING_PAYMENT"   # Payment link sent, waiting


# =============================================================================
# MODELS
# =============================================================================

class Shop(Base):
    __tablename__ = "shops"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    location = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Pricing configuration per shop
    price_per_page_bw = Column(Numeric(10, 2), default=2.00)      # ₹2 per B&W page
    price_per_page_color = Column(Numeric(10, 2), default=10.00)  # ₹10 per color page

    # Relationships
    orders = relationship("Order", back_populates="shop")
    print_jobs = relationship("PrintJob", back_populates="shop")


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_phone = Column(String(50), nullable=False, index=True)
    
    # File info
    file_name = Column(Text)
    file_url = Column(Text)
    file_media_id = Column(String(255))      # Twilio MediaSid for reference
    file_hash = Column(String(64))            # SHA256 hash for duplicate detection
    page_count = Column(Integer, default=1)   # Number of pages in document
    
    # Print configuration
    print_type = Column(Enum(PrintType))      # COLOR, BW, BOTH
    copies = Column(Integer, default=1)
    
    # Pricing
    amount = Column(Numeric(10, 2), default=0)
    
    # Razorpay binding
    razorpay_payment_link_id = Column(String(255), unique=True, index=True)
    razorpay_payment_link_url = Column(Text)
    
    # Status
    order_status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.DRAFT)
    
    # Shop reference
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id", ondelete="SET NULL"))
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    shop = relationship("Shop", back_populates="orders")
    payment = relationship("Payment", back_populates="order", uselist=False, cascade="all, delete-orphan")
    print_job = relationship("PrintJob", back_populates="order", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_orders_shop_status', 'shop_id', 'order_status'),
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Razorpay reference
    provider_reference = Column(String(255))          # razorpay_payment_id
    payment_link_id = Column(String(255), index=True) # plink_xxx for lookup
    
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.INITIATED)
    amount = Column(Numeric(10, 2), nullable=False)
    
    paid_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    order = relationship("Order", back_populates="payment")

    __table_args__ = (
        Index('idx_payments_status', 'payment_status'),
    )


class PrintJob(Base):
    __tablename__ = "print_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    
    printer_name = Column(String(100))
    print_status = Column(Enum(PrintStatus), default=PrintStatus.QUEUED)
    
    # Retry handling
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_error = Column(Text)
    
    printed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    order = relationship("Order", back_populates="print_job")
    shop = relationship("Shop", back_populates="print_jobs")

    __table_args__ = (
        Index('idx_print_jobs_queue', 'shop_id', 'print_status', 'created_at'),
    )


class UserSession(Base):
    """
    Tracks conversation state for each WhatsApp user.
    One active session per phone number.
    """
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(50), nullable=False, unique=True, index=True)
    
    # Current conversation state
    state = Column(Enum(ConversationState), default=ConversationState.IDLE)
    
    # Draft order being built (nullable until order is created)
    draft_order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"))
    
    # Temporary storage during conversation
    temp_file_url = Column(Text)
    temp_file_name = Column(Text)
    temp_file_media_id = Column(String(255))
    temp_print_type = Column(Enum(PrintType))
    
    # Session timing
    last_activity = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    draft_order = relationship("Order", foreign_keys=[draft_order_id])


class WebhookLog(Base):
    """
    Idempotency log for webhooks.
    Prevents duplicate processing of the same webhook event.
    """
    __tablename__ = "webhook_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Unique identifier from provider (e.g., razorpay event id)
    event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)  # 'razorpay', 'twilio'
    
    # Processing result
    processed_at = Column(DateTime, default=datetime.utcnow)
    payload_hash = Column(String(64))  # SHA256 of payload for verification
    
    created_at = Column(DateTime, default=datetime.utcnow)
