"""
Backend API Client for Print Worker

Communicates with AMP K backend to:
- Fetch print job details
- Update job status
- Report errors
"""

import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BackendClient:
    """
    HTTP client for backend API communication.
    
    Uses API key authentication for worker endpoints.
    """
    
    def __init__(self, backend_url: str, api_key: str):
        """
        Initialize backend client.
        
        Args:
            backend_url: Base URL of the backend (e.g., http://localhost:8000)
            api_key: Worker API key for authentication
        """
        self.backend_url = backend_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }
        self.timeout = 30  # seconds
    
    def test_connection(self) -> bool:
        """
        Test connection to backend.
        
        Returns:
            True if backend is reachable, False otherwise
        """
        try:
            response = requests.get(
                f"{self.backend_url}/health",
                timeout=10
            )
            response.raise_for_status()
            health = response.json()
            logger.info(f"Backend health: {health}")
            return health.get('status') in ['healthy', 'degraded']
            
        except requests.RequestException as e:
            logger.error(f"Backend connection test failed: {e}")
            return False
    
    def get_job_details(self, job_id: str) -> Optional[dict]:
        """
        Fetch print job details from backend.
        
        Args:
            job_id: UUID of the print job
            
        Returns:
            Job details dict or None if failed
        """
        try:
            url = f"{self.backend_url}/api/v1/print_jobs/{job_id}"
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            job = response.json()
            logger.info(f"Fetched job {job_id}: {job.get('file_name', 'unknown')}")
            return job
            
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logger.error(f"Job {job_id} not found")
            else:
                logger.error(f"HTTP error fetching job {job_id}: {e}")
            return None
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch job {job_id}: {e}")
            return None
    
    def update_job_status(
        self,
        job_id: str,
        status: str,
        error_message: str = None
    ) -> bool:
        """
        Update print job status in backend.
        
        Args:
            job_id: UUID of the print job
            status: New status (PRINTING, COMPLETED, FAILED)
            error_message: Optional error message for FAILED status
            
        Returns:
            True if update succeeded, False otherwise
        """
        try:
            url = f"{self.backend_url}/api/v1/print_jobs/{job_id}/status"
            
            params = {'status': status}
            if error_message:
                params['error_message'] = error_message
            
            response = requests.put(
                url,
                headers=self.headers,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Updated job {job_id} status to {status}")
            return result.get('status') == 'success'
            
        except requests.HTTPError as e:
            logger.error(f"HTTP error updating job {job_id}: {e.response.text if e.response else e}")
            return False
            
        except requests.RequestException as e:
            logger.error(f"Failed to update job {job_id} status: {e}")
            return False
    
    def download_file(self, file_url: str) -> Optional[bytes]:
        """
        Download file content from backend.
        
        This is a convenience method if file_downloader is not used.
        
        Args:
            file_url: Full URL to the file
            
        Returns:
            File content as bytes or None if failed
        """
        try:
            response = requests.get(
                file_url,
                headers=self.headers,
                timeout=60,
                stream=True
            )
            response.raise_for_status()
            
            content = b''
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk
            
            logger.info(f"Downloaded file: {len(content)} bytes")
            return content
            
        except requests.RequestException as e:
            logger.error(f"Failed to download file from {file_url}: {e}")
            return None
