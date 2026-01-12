"""
AMP K Print Worker

Local Windows PC worker that:
1. Listens to Redis queue for print jobs
2. Downloads files from backend
3. Sends files to printer
4. Updates job status via backend API

Runs as a Windows service or console application.
"""

import json
import time
import logging
import sys
import os
import signal
import redis
from typing import Optional
from backend_client import BackendClient
from file_downloader import FileDownloader
from printer import Printer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('print_worker.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = 'config.json') -> dict:
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Validate required fields
        required = ['backend_url', 'api_key', 'redis_url']
        for field in required:
            if field not in config:
                raise ValueError(f"Missing required config field: {field}")
        
        return config
        
    except FileNotFoundError:
        logger.error(f"Config file {config_path} not found.")
        logger.info("Creating sample config file...")
        sample_config = {
            "backend_url": "http://localhost:8000",
            "api_key": "your-worker-api-key",
            "redis_url": "redis://localhost:6379/0",
            "queue_name": "print_queue",
            "printer_name": "",
            "poll_timeout": 30,
            "max_retries": 3,
            "retry_delay": 5
        }
        with open(config_path, 'w') as f:
            json.dump(sample_config, f, indent=4)
        logger.info(f"Sample config created at {config_path}. Please update it and restart.")
        sys.exit(1)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        sys.exit(1)


class PrintWorker:
    """
    Main print worker class.
    
    Implements Redis consumer pattern with:
    - Blocking pop for efficient queue consumption
    - Job processing with retry logic
    - Graceful shutdown handling
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.running = False
        
        # Initialize components
        self.backend = BackendClient(
            backend_url=config['backend_url'],
            api_key=config['api_key']
        )
        self.downloader = FileDownloader(api_key=config['api_key'])
        self.printer = Printer(printer_name=config.get('printer_name'))
        
        # Redis connection
        self.redis: Optional[redis.Redis] = None
        self.queue_name = config.get('queue_name', 'print_queue')
        self.poll_timeout = config.get('poll_timeout', 30)
        
        # Retry settings
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay = config.get('retry_delay', 5)
        
    def connect_redis(self) -> bool:
        """Connect to Redis server."""
        try:
            self.redis = redis.from_url(
                self.config['redis_url'],
                decode_responses=True,
                socket_connect_timeout=5
            )
            self.redis.ping()
            logger.info(f"Connected to Redis: {self.config['redis_url']}")
            return True
            
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False
    
    def start(self):
        """Start the worker main loop."""
        logger.info("=" * 60)
        logger.info("AMP K Print Worker Starting")
        logger.info("=" * 60)
        
        # Connect to Redis
        if not self.connect_redis():
            logger.error("Cannot start without Redis connection")
            sys.exit(1)
        
        # Test backend connection
        if not self.backend.test_connection():
            logger.warning("Backend connection failed - will retry during operation")
        
        # Check printer
        available_printers = self.printer.get_available_printers()
        logger.info(f"Available printers: {available_printers}")
        
        if self.printer.printer_name:
            logger.info(f"Using printer: {self.printer.printer_name}")
        else:
            logger.info("Using system default printer")
        
        self.running = True
        logger.info(f"Listening for jobs on queue: {self.queue_name}")
        logger.info("-" * 60)
        
        # Main loop
        while self.running:
            try:
                self.process_next_job()
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                self.running = False
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                time.sleep(5)  # Brief pause before retrying
        
        logger.info("Print worker stopped")
    
    def process_next_job(self):
        """
        Wait for and process the next job from the queue.
        
        Uses BLPOP for efficient blocking wait.
        """
        try:
            # BLPOP blocks until an item is available
            # Returns tuple: (queue_name, value) or None on timeout
            result = self.redis.blpop(self.queue_name, timeout=self.poll_timeout)
            
            if result is None:
                # Timeout - no jobs available
                return
            
            _, job_id = result
            logger.info(f"Received job: {job_id}")
            
            # Process the job
            self.handle_job(job_id)
            
        except redis.ConnectionError as e:
            logger.error(f"Redis connection lost: {e}")
            time.sleep(5)
            self.connect_redis()
    
    def handle_job(self, job_id: str):
        """
        Handle a single print job.
        
        Steps:
        1. Fetch job details from backend
        2. Update status to PRINTING
        3. Download file
        4. Print file
        5. Update status to COMPLETED or FAILED
        6. Cleanup temporary files
        """
        temp_file = None
        
        try:
            # 1. Fetch job details
            job = self.backend.get_job_details(job_id)
            
            if not job:
                logger.error(f"Failed to fetch job details for {job_id}")
                return
            
            file_url = job.get('file_url')
            file_name = job.get('file_name', 'document')
            copies = job.get('copies', 1)
            print_type = job.get('print_type', 'BW')
            
            logger.info(f"Processing: {file_name} ({copies} copies, {print_type})")
            
            # 2. Update status to PRINTING
            self.backend.update_job_status(job_id, 'PRINTING')
            
            # 3. Download file
            temp_file = self.downloader.download_file(file_url, file_name)
            
            if not temp_file:
                raise Exception("Failed to download file")
            
            logger.info(f"File downloaded: {temp_file}")
            
            # 4. Print file
            success = self.printer.print_file(
                file_path=temp_file,
                copies=copies,
                print_type=print_type
            )
            
            # 5. Update status
            if success:
                self.backend.update_job_status(job_id, 'COMPLETED')
                logger.info(f"Job {job_id} completed successfully")
            else:
                raise Exception("Print operation failed")
            
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            self.backend.update_job_status(job_id, 'FAILED', error_message=str(e))
            
        finally:
            # 6. Cleanup
            if temp_file:
                self.downloader.cleanup_file(temp_file)
    
    def stop(self):
        """Gracefully stop the worker."""
        logger.info("Stopping print worker...")
        self.running = False


def main():
    """Main entry point."""
    # Handle signals for graceful shutdown
    worker = None
    
    def signal_handler(sig, frame):
        if worker:
            worker.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Load configuration
    config = load_config()
    
    # Create and start worker
    worker = PrintWorker(config)
    worker.start()


if __name__ == "__main__":
    main()
