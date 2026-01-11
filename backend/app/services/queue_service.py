from app.core.redis_client import get_redis_client
import logging

QUEUE_NAME = "print_queue"
logger = logging.getLogger(__name__)

def enqueue_print_job(print_job_id: str):
    try:
        redis_client = get_redis_client()
        redis_client.lpush(QUEUE_NAME, print_job_id)
        logger.info(f"Enqueued job {print_job_id} to {QUEUE_NAME}")
    except Exception as e:
        logger.error(f"Failed to enqueue job {print_job_id}: {e}")
        # In a real system, you might want to retry or mark DB as failed to queue
