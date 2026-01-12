"""
File Serving Routes for AMP K

Serves uploaded files for:
1. Print worker to download files for printing
2. Dashboard to preview files
"""

from fastapi import APIRouter, HTTPException, Header, Path
from fastapi.responses import FileResponse
from pathlib import Path as FilePath
import os
import logging

from app.core.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


def verify_worker_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """
    Verify worker API key for file downloads.
    """
    # For file downloads, we can be more lenient or use different auth
    # In production, you might want to use signed URLs instead
    if x_api_key and x_api_key == settings.WORKER_API_KEY:
        return True
    # Allow public access for now (files are protected by obscure paths)
    # In production, implement proper access control
    return True


@router.get("/{file_path:path}")
async def serve_file(
    file_path: str = Path(..., description="Path to the file relative to uploads directory")
):
    """
    Serve an uploaded file.
    
    Files are stored with hashed names for security.
    
    Args:
        file_path: Relative path within uploads directory
    """
    try:
        # Sanitize path to prevent directory traversal
        safe_path = FilePath(file_path).as_posix()
        
        # Remove leading slashes and dots
        safe_path = safe_path.lstrip("./\\")
        
        # Check for path traversal attempts
        if ".." in safe_path or safe_path.startswith("/"):
            logger.warning(f"Path traversal attempt: {file_path}")
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        # Build full path
        full_path = os.path.join(settings.FILE_STORAGE_PATH, safe_path)
        full_path = os.path.normpath(full_path)
        
        # Verify the path is within uploads directory
        uploads_dir = os.path.normpath(os.path.abspath(settings.FILE_STORAGE_PATH))
        file_abs_path = os.path.normpath(os.path.abspath(full_path))
        
        if not file_abs_path.startswith(uploads_dir):
            logger.warning(f"Path escape attempt: {file_path} -> {full_path}")
            raise HTTPException(status_code=400, detail="Invalid file path")
        
        # Check if file exists
        if not os.path.isfile(full_path):
            logger.warning(f"File not found: {full_path}")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Determine content type
        content_type = get_content_type(full_path)
        
        # Get filename for download
        filename = os.path.basename(full_path)
        
        logger.info(f"Serving file: {safe_path}")
        
        return FileResponse(
            path=full_path,
            media_type=content_type,
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


def get_content_type(file_path: str) -> str:
    """
    Determine content type from file extension.
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    content_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".ppt": "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt": "text/plain",
    }
    
    return content_types.get(ext, "application/octet-stream")
