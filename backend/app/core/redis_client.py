import redis
from app.core.config import get_settings

settings = get_settings()

# Initialize Redis Client
# Decode responses to get strings instead of bytes
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True) if hasattr(settings, 'REDIS_URL') else redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def get_redis_client():
    return redis_client
