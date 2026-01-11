from app.core.redis_client import redis_client

QUEUE_NAME = "print_queue"

def enqueue_print_job(print_job_id: str):
    redis_client.lpush(QUEUE_NAME, print_job_id)
