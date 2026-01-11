from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.models import PrintJob, PrintStatus, Order
import logging
from uuid import UUID

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/{job_id}")
async def get_print_job(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Fetch print job details for the worker.
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
            
        return {
            "id": job.id,
            "file_url": job.order.file_url,
            "filename": job.order.file_name,
            "copies": job.order.copies,
            "printer_name": job.printer_name,
            "status": job.print_status
        }
    except Exception as e:
        logger.error(f"Error fetching job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.put("/{job_id}/status")
async def update_print_job_status(job_id: UUID, status: str, db: AsyncSession = Depends(get_db)):
    """
    Update the status of a print job (e.g. PRINTING, COMPLETED, FAILED).
    """
    try:
        result = await db.execute(select(PrintJob).where(PrintJob.id == job_id))
        job = result.scalars().first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Print job not found")
        
        # Validate status
        if status not in PrintStatus.__members__:
             raise HTTPException(status_code=400, detail="Invalid status")

        job.print_status = PrintStatus[status]
        
        # If successfully printed, update timestamp
        if status == "COMPLETED":
            from datetime import datetime
            job.printed_at = datetime.utcnow()
            
        await db.commit()
        await db.refresh(job)
        
        return {"status": "success", "job_status": job.print_status}
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")
