"""
File Downloader for Print Worker

Downloads files from backend and manages temporary storage.
"""

import requests
import tempfile
import os
import logging
from typing import Optional
from urllib.parse import urlparse, unquote

logger = logging.getLogger(__name__)


class FileDownloader:
    """
    Handles file downloads and temporary file management.
    
    Features:
    - Authenticated downloads from backend
    - Automatic extension detection
    - Temporary file management
    - Cleanup utilities
    """
    
    def __init__(self, api_key: str = None, temp_dir: str = None):
        """
        Initialize file downloader.
        
        Args:
            api_key: API key for authenticated downloads
            temp_dir: Directory for temporary files (uses system temp if None)
        """
        self.api_key = api_key
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.headers = {}
        
        if self.api_key:
            self.headers['X-API-Key'] = self.api_key
        
        self.timeout = 120  # 2 minutes for large files
        
        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
    
    def download_file(
        self,
        file_url: str,
        filename_hint: str = None
    ) -> Optional[str]:
        """
        Download a file and save to temporary location.
        
        Args:
            file_url: URL to download from
            filename_hint: Hint for filename/extension
            
        Returns:
            Path to downloaded file or None if failed
        """
        try:
            logger.info(f"Downloading: {file_url}")
            
            response = requests.get(
                file_url,
                headers=self.headers,
                timeout=self.timeout,
                stream=True
            )
            response.raise_for_status()
            
            # Determine file extension
            ext = self._get_extension(file_url, filename_hint, response)
            
            # Create temporary file with proper extension
            fd, temp_path = tempfile.mkstemp(suffix=ext, dir=self.temp_dir)
            
            # Write content
            bytes_written = 0
            with os.fdopen(fd, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        bytes_written += len(chunk)
            
            logger.info(f"Downloaded {bytes_written} bytes to {temp_path}")
            return temp_path
            
        except requests.HTTPError as e:
            logger.error(f"HTTP error downloading file: {e.response.status_code}")
            return None
            
        except requests.RequestException as e:
            logger.error(f"Failed to download file from {file_url}: {e}")
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error downloading file: {e}")
            return None
    
    def _get_extension(
        self,
        url: str,
        filename_hint: str,
        response: requests.Response
    ) -> str:
        """
        Determine file extension from various sources.
        
        Priority:
        1. Content-Disposition header
        2. filename_hint parameter
        3. URL path
        4. Content-Type header
        5. Default to .bin
        """
        # Try Content-Disposition header
        content_disp = response.headers.get('content-disposition', '')
        if 'filename=' in content_disp:
            filename = content_disp.split('filename=')[-1].strip('"\'')
            ext = os.path.splitext(filename)[1]
            if ext:
                return ext
        
        # Try filename hint
        if filename_hint:
            ext = os.path.splitext(filename_hint)[1]
            if ext:
                return ext
        
        # Try URL path
        parsed = urlparse(url)
        path = unquote(parsed.path)
        ext = os.path.splitext(path)[1]
        if ext:
            return ext
        
        # Try Content-Type
        content_type = response.headers.get('content-type', '')
        ext = self._extension_from_content_type(content_type)
        if ext:
            return ext
        
        return '.bin'
    
    def _extension_from_content_type(self, content_type: str) -> str:
        """Map content type to file extension."""
        # Get main type without parameters
        main_type = content_type.split(';')[0].strip().lower()
        
        mapping = {
            'application/pdf': '.pdf',
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'application/msword': '.doc',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
            'application/vnd.ms-excel': '.xls',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
            'application/vnd.ms-powerpoint': '.ppt',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
            'text/plain': '.txt',
            'application/octet-stream': '.bin',
        }
        
        return mapping.get(main_type, '')
    
    def cleanup_file(self, file_path: str) -> bool:
        """
        Delete a temporary file.
        
        Args:
            file_path: Path to file to delete
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up: {file_path}")
                return True
            return False
            
        except OSError as e:
            logger.error(f"Failed to delete {file_path}: {e}")
            return False
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """
        Clean up old temporary files.
        
        Useful for periodic maintenance.
        
        Args:
            max_age_hours: Delete files older than this
        """
        import time
        
        cutoff = time.time() - (max_age_hours * 3600)
        cleaned = 0
        
        try:
            for filename in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, filename)
                
                if os.path.isfile(file_path):
                    if os.path.getmtime(file_path) < cutoff:
                        try:
                            os.remove(file_path)
                            cleaned += 1
                        except OSError:
                            pass
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} old temporary files")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
