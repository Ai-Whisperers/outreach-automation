"""
Redis Cache for LLM Responses
===============================

Provides semantic caching for expensive LLM calls using Redis and langchain-redis.
"""

import logging

import redis
from langchain_core.caches import BaseCache
from langchain_openai import OpenAIEmbeddings
from langchain_redis import RedisCache, RedisSemanticCache

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_redis_cache() -> BaseCache | None:
    """
    Get configured Redis cache for LangChain.

    Returns:
        Redis cache instance or None if disabled/unavailable
    """
    if not settings.redis_enabled:
        logger.info("Redis caching is disabled")
        return None

    try:
        # Test Redis connection
        redis_client = redis.from_url(settings.redis_url)
        redis_client.ping()

        # Use semantic cache (embeddings-based) for better cache hits
        cache = RedisSemanticCache(
            redis_url=settings.redis_url,
            embedding=OpenAIEmbeddings(api_key=settings.openai_api_key),
            ttl=settings.redis_ttl
        )

        logger.info(f"✓ Redis semantic cache enabled (TTL: {settings.redis_ttl}s)")
        return cache

    except redis.ConnectionError as e:
        logger.warning(f"Redis connection failed: {e}. Running without cache.")
        return None
    except Exception as e:
        logger.warning(f"Could not initialize Redis cache: {e}. Running without cache.")
        return None


def get_simple_redis_cache() -> BaseCache | None:
    """
    Get simple Redis cache (exact match only, faster but less flexible).

    Returns:
        Simple Redis cache or None if unavailable
    """
    if not settings.redis_enabled:
        return None

    try:
        redis_client = redis.from_url(settings.redis_url)
        redis_client.ping()

        cache = RedisCache(
            redis_url=settings.redis_url,
            ttl=settings.redis_ttl
        )

        logger.info(f"✓ Redis cache enabled (TTL: {settings.redis_ttl}s)")
        return cache

    except Exception as e:
        logger.warning(f"Redis cache unavailable: {e}")
        return None
