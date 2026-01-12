"""
Dashboard API for AMP K

Provides endpoints for:
- Order statistics and revenue tracking
- Live order status monitoring
- Print queue status
- Failed job management
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, case
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
import logging

from app.core.database import get_db
from app.models import Order, OrderStatus, Payment, PaymentStatus, PrintJob, PrintStatus, Shop

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/stats")
async def get_dashboard_stats(
    shop_id: Optional[UUID] = None,
    days: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """
    Get dashboard statistics.
    
    Returns:
    - Total orders (by status)
    - Revenue (today, week, month, total)
    - Print job stats (pending, completed, failed)
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)
        
        # Base conditions
        conditions = [Order.created_at >= start_date]
        if shop_id:
            conditions.append(Order.shop_id == shop_id)
        
        # Order counts by status
        order_stats = await db.execute(
            select(
                Order.order_status,
                func.count(Order.id).label("count")
            )
            .where(and_(*conditions))
            .group_by(Order.order_status)
        )
        order_counts = {row.order_status.value: row.count for row in order_stats.fetchall()}
        
        # Revenue calculation (only PAID orders)
        paid_conditions = conditions + [Order.order_status == OrderStatus.PAID]
        
        # Total revenue
        total_revenue_result = await db.execute(
            select(func.sum(Order.amount))
            .where(and_(*paid_conditions))
        )
        total_revenue = float(total_revenue_result.scalar() or 0)
        
        # Today's revenue
        today_conditions = paid_conditions + [Order.updated_at >= today_start]
        today_revenue_result = await db.execute(
            select(func.sum(Order.amount))
            .where(and_(*today_conditions))
        )
        today_revenue = float(today_revenue_result.scalar() or 0)
        
        # Week's revenue
        week_conditions = paid_conditions + [Order.updated_at >= week_start]
        week_revenue_result = await db.execute(
            select(func.sum(Order.amount))
            .where(and_(*week_conditions))
        )
        week_revenue = float(week_revenue_result.scalar() or 0)
        
        # Month's revenue
        month_conditions = paid_conditions + [Order.updated_at >= month_start]
        month_revenue_result = await db.execute(
            select(func.sum(Order.amount))
            .where(and_(*month_conditions))
        )
        month_revenue = float(month_revenue_result.scalar() or 0)
        
        # Print job stats
        print_conditions = [PrintJob.created_at >= start_date]
        if shop_id:
            print_conditions.append(PrintJob.shop_id == shop_id)
        
        print_stats = await db.execute(
            select(
                PrintJob.print_status,
                func.count(PrintJob.id).label("count")
            )
            .where(and_(*print_conditions))
            .group_by(PrintJob.print_status)
        )
        print_counts = {row.print_status.value: row.count for row in print_stats.fetchall()}
        
        return {
            "period_days": days,
            "orders": {
                "draft": order_counts.get("DRAFT", 0),
                "payment_pending": order_counts.get("PAYMENT_PENDING", 0),
                "paid": order_counts.get("PAID", 0),
                "cancelled": order_counts.get("CANCELLED", 0),
                "total": sum(order_counts.values())
            },
            "revenue": {
                "today": today_revenue,
                "week": week_revenue,
                "month": month_revenue,
                "period_total": total_revenue,
                "currency": "INR"
            },
            "print_jobs": {
                "queued": print_counts.get("QUEUED", 0),
                "printing": print_counts.get("PRINTING", 0),
                "completed": print_counts.get("COMPLETED", 0),
                "failed": print_counts.get("FAILED", 0)
            },
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/orders")
async def list_orders(
    shop_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """
    List orders with optional filters.
    
    For dashboard order management view.
    """
    try:
        query = select(Order)
        
        # Apply filters
        conditions = []
        if shop_id:
            conditions.append(Order.shop_id == shop_id)
        if status_filter:
            status_upper = status_filter.upper()
            if status_upper in OrderStatus.__members__:
                conditions.append(Order.order_status == OrderStatus[status_upper])
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # Order by creation time (newest first)
        query = query.order_by(Order.created_at.desc())
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        orders = result.scalars().all()
        
        # Get total count
        count_query = select(func.count(Order.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        count_result = await db.execute(count_query)
        total_count = count_result.scalar()
        
        return {
            "orders": [
                {
                    "id": str(order.id),
                    "customer_phone": order.customer_phone,
                    "file_name": order.file_name,
                    "print_type": order.print_type.value if order.print_type else None,
                    "copies": order.copies,
                    "amount": float(order.amount) if order.amount else 0,
                    "order_status": order.order_status.value,
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "updated_at": order.updated_at.isoformat() if order.updated_at else None
                }
                for order in orders
            ],
            "total": total_count,
            "offset": offset,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error listing orders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/orders/{order_id}")
async def get_order_details(
    order_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed order information.
    
    Includes payment and print job details.
    """
    try:
        from sqlalchemy.orm import selectinload
        
        result = await db.execute(
            select(Order)
            .options(
                selectinload(Order.payment),
                selectinload(Order.print_job)
            )
            .where(Order.id == order_id)
        )
        order = result.scalars().first()
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        return {
            "id": str(order.id),
            "customer_phone": order.customer_phone,
            "file_name": order.file_name,
            "file_url": order.file_url,
            "print_type": order.print_type.value if order.print_type else None,
            "copies": order.copies,
            "page_count": order.page_count,
            "amount": float(order.amount) if order.amount else 0,
            "order_status": order.order_status.value,
            "razorpay_payment_link_id": order.razorpay_payment_link_id,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            "payment": {
                "id": str(order.payment.id),
                "status": order.payment.payment_status.value,
                "provider_reference": order.payment.provider_reference,
                "amount": float(order.payment.amount),
                "paid_at": order.payment.paid_at.isoformat() if order.payment.paid_at else None
            } if order.payment else None,
            "print_job": {
                "id": str(order.print_job.id),
                "status": order.print_job.print_status.value,
                "retry_count": order.print_job.retry_count,
                "printed_at": order.print_job.printed_at.isoformat() if order.print_job.printed_at else None,
                "last_error": order.print_job.last_error
            } if order.print_job else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order {order_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/pending-jobs")
async def get_pending_jobs(
    shop_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all pending print jobs.
    
    Useful for monitoring the print queue.
    """
    try:
        from sqlalchemy.orm import selectinload
        
        conditions = [PrintJob.print_status.in_([PrintStatus.QUEUED, PrintStatus.PRINTING])]
        if shop_id:
            conditions.append(PrintJob.shop_id == shop_id)
        
        result = await db.execute(
            select(PrintJob)
            .options(selectinload(PrintJob.order))
            .where(and_(*conditions))
            .order_by(PrintJob.created_at.asc())  # FIFO order
        )
        jobs = result.scalars().all()
        
        return {
            "pending_jobs": [
                {
                    "id": str(job.id),
                    "order_id": str(job.order_id),
                    "file_name": job.order.file_name if job.order else None,
                    "copies": job.order.copies if job.order else 1,
                    "print_status": job.print_status.value,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "customer_phone": job.order.customer_phone if job.order else None
                }
                for job in jobs
            ],
            "total": len(jobs)
        }
        
    except Exception as e:
        logger.error(f"Error fetching pending jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/failed-jobs")
async def get_failed_jobs(
    shop_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all failed print jobs for manual intervention.
    """
    try:
        from sqlalchemy.orm import selectinload
        
        conditions = [PrintJob.print_status == PrintStatus.FAILED]
        if shop_id:
            conditions.append(PrintJob.shop_id == shop_id)
        
        result = await db.execute(
            select(PrintJob)
            .options(selectinload(PrintJob.order))
            .where(and_(*conditions))
            .order_by(PrintJob.updated_at.desc())
        )
        jobs = result.scalars().all()
        
        return {
            "failed_jobs": [
                {
                    "id": str(job.id),
                    "order_id": str(job.order_id),
                    "file_name": job.order.file_name if job.order else None,
                    "retry_count": job.retry_count,
                    "max_retries": job.max_retries,
                    "last_error": job.last_error,
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                    "customer_phone": job.order.customer_phone if job.order else None
                }
                for job in jobs
            ],
            "total": len(jobs)
        }
        
    except Exception as e:
        logger.error(f"Error fetching failed jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")
