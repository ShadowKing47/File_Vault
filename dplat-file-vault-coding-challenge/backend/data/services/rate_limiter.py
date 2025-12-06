import logging
import time

try:
    import redis
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    REDIS_AVAILABLE = True
except (ImportError, redis.ConnectionError):
    redis_client = None
    REDIS_AVAILABLE = False

from django.conf import settings
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def sliding_window(limit: int, window_sec: int):
    """Rate limiting decorator using Redis sliding window algorithm"""
    def decorator(view_func):
        def wrapper(view, request, *args, **kwargs):
            if not REDIS_AVAILABLE:
                logger.warning("Redis not available, rate limiting disabled")
                return view_func(view, request, *args, **kwargs)

            user_id = request.user.id if request.user.is_authenticated else None
            if not user_id:
                return view_func(view, request, *args, **kwargs)

            key = f"rate:{user_id}"
            now = int(time.time())

            try:
                redis_client.zadd(key, {str(now): now})
                redis_client.zremrangebyscore(key, 0, now - window_sec)
                redis_client.expire(key, window_sec)
                count = redis_client.zcard(key)

                if count > limit:
                    logger.warning(
                        "Rate limit exceeded",
                        extra={"user_id": user_id, "count": count, "limit": limit}
                    )
                    return Response(
                        {"error": "Too many requests. Please try again later."},
                        status=status.HTTP_429_TOO_MANY_REQUESTS
                    )
            except Exception as e:
                logger.exception("Error in rate limiting", extra={"user_id": user_id})
                # If Redis fails, allow the request to proceed
                pass

            return view_func(view, request, *args, **kwargs)
        return wrapper
    return decorator