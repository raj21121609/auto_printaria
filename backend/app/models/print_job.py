from sqlalchemy import Column, String, ForeignKey, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base

class PrintJob(Base):
    __tablename__ = "print_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"))
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"))
    print_status = Column(String)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
