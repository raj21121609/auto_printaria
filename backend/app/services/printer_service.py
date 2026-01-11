import os
import httpx
import aiofiles
import logging
import subprocess
import asyncio
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

async def download_file(url: str, destination: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            async with aiofiles.open(destination, mode='wb') as f:
                await f.write(response.content)
            return True
        else:
            logger.error(f"Failed to download file from {url}")
            return False

async def print_document(file_url: str):
    """
    Downloads the file and sends it to the system printer.
    """
    # Create temp directory
    temp_dir = "temp_downloads"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Extract filename or generate one
    filename = file_url.split("/")[-1] or "document.pdf"
    # Basic sanitization
    filename = "".join([c for c in filename if c.isalnum() or c in "._-"])
    file_path = os.path.join(temp_dir, filename)
    
    logger.info(f"Downloading file for printing: {file_url}")
    if await download_file(file_url, file_path):
        logger.info(f"File downloaded to {file_path}. Sending to printer...")
        
        try:
            # Windows Print Command
            # Uses built-in 'print' or 'start' command
            # 'start /min /wait print /d:printer "file"' is one way, but
            # simple 'os.startfile' with "print" verb works well on Windows for default printer.
            
            # Using Powershell to print might be more robust for specific printers
            # Start-Process -FilePath "path" -Verb Print
            
            cmd = f'Start-Process -FilePath "{file_path}" -Verb Print -PassThru | ForEach-Object {{ $_.WaitForExit() }}'
            
            # Use asyncio to run the subprocess separately
            process = await asyncio.create_subprocess_shell(
                f"powershell -Command \"{cmd}\"",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("Print command executed successfully.")
                return True
            else:
                logger.error(f"Print command failed: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Exception during printing: {e}")
            return False
    else:
        logger.error("Download failed, cannot print.")
        return False
