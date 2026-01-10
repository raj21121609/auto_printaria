import json
import time
import logging
import sys
import os
from backend_client import BackendClient
from file_downloader import FileDownloader
from printer import Printer

def load_config(config_path='config.json'):
    """
    Load configuration from JSON file.
    """
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Config file {config_path} not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in config file: {e}")
        sys.exit(1)

def process_job(job, backend_client, downloader, printer):
    """
    Process a single print job: download, print, update status, cleanup.
    """
    job_id = job.get('id')
    file_url = job.get('file_url')
    copies = job.get('copies', 1)
    
    if not job_id or not file_url:
        logging.warning(f"Invalid job data: {job}")
        return
    
    # Download file
    temp_path = downloader.download_file(file_url)
    if not temp_path:
        logging.error(f"Failed to download file for job {job_id}")
        return
    
    try:
        # Print file
        if printer.print_file(temp_path, copies):
            # Update status to PRINTED
            if backend_client.update_job_status(job_id, 'PRINTED'):
                logging.info(f"Successfully processed job {job_id}")
            else:
                logging.error(f"Failed to update status for job {job_id}")
        else:
            logging.error(f"Failed to print job {job_id}")
    finally:
        # Cleanup temporary file
        downloader.cleanup_file(temp_path)

def main():
    """
    Main polling loop for the print worker.
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    config = load_config()
    backend_url = config['backend_url']
    shop_id = config['shop_id']
    auth_token = config['auth_token']
    poll_interval = config['poll_interval']
    
    backend_client = BackendClient(backend_url, auth_token)
    downloader = FileDownloader(auth_token)  # Use token for downloads if needed
    printer = Printer()
    
    logging.info("Print worker started. Polling for jobs...")
    
    try:
        while True:
            jobs = backend_client.get_pending_jobs(shop_id)
            if jobs is not None:
                for job in jobs:
                    process_job(job, backend_client, downloader, printer)
            else:
                logging.warning("Failed to fetch jobs, will retry in next poll.")
            
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logging.info("Print worker stopped by user.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()