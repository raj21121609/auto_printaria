"""
Print Jobs API for AMP K

Endpoints used by:
1. Print Worker (local PC) - to fetch job details and update status
2. Dashboard - to view job status
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_
from datetime import datetime
from typing import Optional
from uuid import UUID
import os
import logging

from app.core.database import get_db
from app.core.config import get_settings
from app.models import PrintJob, PrintStatus, Order, OrderStatus
from app.services import twilio_service

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


def verify_worker_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """
    Verify worker API key for protected endpoints.
    """
    if not x_api_key or x_api_key != settings.WORKER_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )
    return True


@router.get("/{job_id}")
async def get_print_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_worker_api_key)
):
    """
    Fetch print job details for the worker.
    
    Called by print worker after receiving job ID from Redis queue.
    
    Returns all information needed to execute the print job:
    - File URL for download
    - Print configuration (copies, print type)
    - Job metadata
    """
    try:
        result = await db.execute(
            select(PrintJob)
            .options(selectinload(PrintJob.order))
            .where(PrintJob.id == job_id)
        )
        job = result.scalars().first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Print job not found")
        
        order = job.order
        
        return {
            "id": str(job.id),
            "order_id": str(job.order_id),
            "file_url": order.file_url,
            "file_name": order.file_name,
            "copies": order.copies,
            "print_type": order.print_type.value if order.print_type else "BW",
            "customer_phone": order.customer_phone,
            "print_status": job.print_status.value,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
            "created_at": job.created_at.isoformat() if job.created_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.put("/{job_id}/status")
async def update_print_job_status(
    job_id: UUID,
    status_update: str = Query(..., alias="status"),
    error_message: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_worker_api_key)
):
    """
    Update the status of a print job.
    
    Called by print worker to report progress:
    - PRINTING: Job started
    - COMPLETED: Job finished successfully
    - FAILED: Job failed (with optional error message)
    
    Args:
        job_id: Print job UUID
        status: New status (PRINTING, COMPLETED, FAILED)
        error_message: Optional error message for FAILED status
    """
    try:
        result = await db.execute(
            select(PrintJob)
            .options(selectinload(PrintJob.order))
            .where(PrintJob.id == job_id)
        )
        job = result.scalars().first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Print job not found")
        
        # Validate status
        status_upper = status_update.upper()
        if status_upper not in PrintStatus.__members__:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_update}")
        
        new_status = PrintStatus[status_upper]
        old_status = job.print_status
        
        # Update job
        job.print_status = new_status
        
        if new_status == PrintStatus.COMPLETED:
            job.printed_at = datetime.utcnow()
            # Send completion notification to customer
            await send_print_notification(job.order, success=True)
            
        elif new_status == PrintStatus.FAILED:
            job.last_error = error_message
            job.retry_count += 1
            
            # Check if we should notify customer
            if job.retry_count >= job.max_retries:
                await send_print_notification(job.order, success=False)
        
        await db.commit()
        await db.refresh(job)
        
        logger.info(f"Job {job_id}: {old_status} -> {new_status}")
        
        return {
            "status": "success",
            "job_id": str(job.id),
            "print_status": job.print_status.value,
            "retry_count": job.retry_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("")
async def list_print_jobs(
    shop_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_worker_api_key)
):
    """
    List print jobs with optional filters.
    
    Used by dashboard and worker for monitoring.
    """
    try:
        query = select(PrintJob).options(selectinload(PrintJob.order))
        
        # Apply filters
        conditions = []
        if shop_id:
            conditions.append(PrintJob.shop_id == shop_id)
        if status_filter:
            status_upper = status_filter.upper()
            if status_upper in PrintStatus.__members__:
                conditions.append(PrintJob.print_status == PrintStatus[status_upper])
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # Order by creation time (newest first)
        query = query.order_by(PrintJob.created_at.desc())
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        jobs = result.scalars().all()
        
        return {
            "jobs": [
                {
                    "id": str(job.id),
                    "order_id": str(job.order_id),
                    "file_name": job.order.file_name if job.order else None,
                    "print_status": job.print_status.value,
                    "retry_count": job.retry_count,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                    "printed_at": job.printed_at.isoformat() if job.printed_at else None
                }
                for job in jobs
            ],
            "total": len(jobs),
            "offset": offset,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error listing jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/{job_id}/retry")
async def retry_print_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_worker_api_key)
):
    """
    Manually retry a failed print job.
    
    Resets status to QUEUED and re-enqueues to Redis.
    """
    from app.services.queue_service import enqueue_print_job
    
    try:
        result = await db.execute(
            select(PrintJob).where(PrintJob.id == job_id)
        )
        job = result.scalars().first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Print job not found")
        
        if job.print_status != PrintStatus.FAILED:
            raise HTTPException(
                status_code=400,
                detail=f"Can only retry FAILED jobs, current status: {job.print_status.value}"
            )
        
        # Reset job
        job.print_status = PrintStatus.QUEUED
        job.last_error = None
        # Don't reset retry_count to track total attempts
        
        await db.commit()
        
        # Re-enqueue
        enqueue_print_job(str(job.id))
        
        logger.info(f"Job {job_id} retried, re-queued")
        
        return {"status": "success", "message": "Job re-queued for printing"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def send_print_notification(order: Order, success: bool):
    """
    Send WhatsApp notification about print completion.
    """
    if not order or not order.customer_phone:
        return
    
    try:
        if success:
            message = twilio_service.msg_print_complete(str(order.id))
        else:
            message = twilio_service.msg_print_failed(str(order.id))
        
        await twilio_service.send_whatsapp_message(
            to=order.customer_phone,
            body=message
        )
        
        logger.info(f"Print notification sent to {order.customer_phone}, success={success}")
        
    except Exception as e:
        logger.error(f"Failed to send print notification: {e}")
