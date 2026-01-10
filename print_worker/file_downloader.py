import requests
import tempfile
import os
import logging

class FileDownloader:
    def __init__(self, auth_token=None):
        self.auth_token = auth_token
        self.headers = {}
        if self.auth_token:
            self.headers['Authorization'] = f'Bearer {self.auth_token}'

    def download_file(self, file_url):
        """
        Download the file from the given URL and save it to a temporary location.
        Returns the temporary file path if successful, None otherwise.
        """
        try:
            response = requests.get(file_url, headers=self.headers, timeout=30, stream=True)
            response.raise_for_status()
            
            # Create a temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(file_url)[1] or '.tmp')
            with os.fdopen(temp_fd, 'wb') as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
            
            logging.info(f"Downloaded file to {temp_path}")
            return temp_path
        except requests.RequestException as e:
            logging.error(f"Failed to download file from {file_url}: {e}")
            return None

    def cleanup_file(self, file_path):
        """
        Delete the temporary file.
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Cleaned up temporary file {file_path}")
        except OSError as e:
            logging.error(f"Failed to delete temporary file {file_path}: {e}")