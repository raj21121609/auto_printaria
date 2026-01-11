import json
import time
import logging
import sys
import os
import redis
from backend_client import BackendClient
from file_downloader import FileDownloader
from printer import Printer

def load_config(config_path='config.json'):
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Config file {config_path} not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON in config file: {e}")
        sys.exit(1)

def main():
    """
    Main loop for the print worker (Redis Consumer).
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    config = load_config()
    backend_url = config['backend_url']
    shop_id = config.get('shop_id') # Might not strictly need this for popping if using a specific queue key
    auth_token = config['auth_token']
    redis_url = config.get('redis_url', 'redis://localhost:6379/0')
    queue_name = config.get('queue_name', 'print_queue')
    
    backend_client = BackendClient(backend_url, auth_token)
    downloader = FileDownloader(auth_token)
    printer = Printer()
    
    # Connect to Redis
    try:
        r = redis.from_url(redis_url, decode_responses=True)
        r.ping()
        logging.info(f"Connected to Redis at {redis_url}")
    except redis.ConnectionError as e:
        logging.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)
    
    logging.info(f"Print worker started. Waiting for jobs on queue: {queue_name}...")
    
    try:
        while True:
            # BLPOP blocks until an item is available
            # Returns tuple (queue_name, value)
            # Timeout 0 means block indefinitely
            item = r.blpop(queue_name, timeout=0) 
            
            if item:
                _, job_id = item
                logging.info(f"Received Job ID: {job_id}")
                
                # Fetch Job Details
                job_details = backend_client.get_job_details(job_id)
                
                if job_details:
                     process_job(job_details, backend_client, downloader, printer)
                else:
                    logging.error(f"Could not fetch details for job {job_id}")

    except KeyboardInterrupt:
        logging.info("Print worker stopped by user.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)

def process_job(job, backend_client, downloader, printer):
    job_id = job.get('id')
    file_url = job.get('file_url')
    copies = job.get('copies', 1)
    
    logging.info(f"Processing Job {job_id}: {file_url} ({copies} copies)")
    
    # Update Status -> PRINTING
    backend_client.update_job_status(job_id, 'PRINTING')
    
    temp_path = downloader.download_file(file_url)
    if not temp_path:
        logging.error(f"Failed to download file for job {job_id}")
        backend_client.update_job_status(job_id, 'FAILED')
        return

    try:
        if printer.print_file(temp_path, copies):
            backend_client.update_job_status(job_id, 'COMPLETED')
            logging.info(f"Successfully processed job {job_id}")
        else:
            backend_client.update_job_status(job_id, 'FAILED')
            logging.error(f"Failed to print job {job_id}")
    except Exception as e:
        logging.error(f"Error during printing job {job_id}: {e}")
        backend_client.update_job_status(job_id, 'FAILED')
    finally:
        downloader.cleanup_file(temp_path)

if __name__ == "__main__":
    main()
