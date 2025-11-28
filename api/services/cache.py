"""
Caching Service

Provides in-memory and file-based caching for AI responses and other expensive operations.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger("cache")


class CacheEntry:
    """Represents a cached value with metadata."""

    def __init__(self, value: Any, ttl_seconds: int):
        self.value = value
        self.created_at = time.time()
        self.ttl_seconds = ttl_seconds

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        if self.ttl_seconds <= 0:
            return False  # Never expires
        return time.time() > (self.created_at + self.ttl_seconds)


class MemoryCache:
    """
    In-memory cache with TTL support.

    Thread-safe for single-process use. For multi-process,
    consider using Redis or similar.
    """

    def __init__(self, default_ttl: int = 3600):
        """
        Initialize memory cache.

        Args:
            default_ttl: Default time-to-live in seconds (default: 1 hour)
        """
        self._cache: dict[str, CacheEntry] = {}
        self.default_ttl = default_ttl
        self._hit_count = 0
        self._miss_count = 0
        logger.info(f"Memory cache initialized with TTL: {default_ttl}s")

    def _generate_key(self, *args, **kwargs) -> str:
        """Generate a cache key from arguments."""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        entry = self._cache.get(key)

        if entry is None:
            self._miss_count += 1
            return None

        if entry.is_expired():
            del self._cache[key]
            self._miss_count += 1
            logger.debug(f"Cache expired: {key[:16]}...")
            return None

        self._hit_count += 1
        logger.debug(f"Cache hit: {key[:16]}...")
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Set a value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        if ttl is None:
            ttl = self.default_ttl

        self._cache[key] = CacheEntry(value, ttl)
        logger.debug(f"Cache set: {key[:16]}... (TTL: {ttl}s)")

    def delete(self, key: str) -> bool:
        """
        Delete a value from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> int:
        """
        Clear all cached values.

        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared: {count} entries")
        return count

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired entries")

        return len(expired_keys)

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total_requests * 100) if total_requests > 0 else 0

        return {
            "entries": len(self._cache),
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": f"{hit_rate:.1f}%"
        }


class FileCache:
    """
    File-based cache for persistent storage.

    Uses JSON files for storing cached responses.
    """

    def __init__(self, cache_dir: Path | None = None, default_ttl: int = 86400):
        """
        Initialize file cache.

        Args:
            cache_dir: Directory for cache files
            default_ttl: Default time-to-live in seconds (default: 24 hours)
        """
        if cache_dir is None:
            settings = get_settings()
            cache_dir = settings.projects_dir / ".cache"

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl
        logger.info(f"File cache initialized at: {cache_dir}")

    def _get_cache_path(self, key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Any | None:
        """
        Get a value from file cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)

            # Check expiration
            created_at = data.get("created_at", 0)
            ttl = data.get("ttl", self.default_ttl)

            if ttl > 0 and time.time() > (created_at + ttl):
                cache_path.unlink()
                logger.debug(f"File cache expired: {key[:16]}...")
                return None

            logger.debug(f"File cache hit: {key[:16]}...")
            return data.get("value")

        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read cache file: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Set a value in file cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
        """
        if ttl is None:
            ttl = self.default_ttl

        cache_path = self._get_cache_path(key)

        data = {
            "value": value,
            "created_at": time.time(),
            "ttl": ttl
        }

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"File cache set: {key[:16]}...")
        except OSError as e:
            logger.error(f"Failed to write cache file: {e}")

    def delete(self, key: str) -> bool:
        """Delete a value from file cache."""
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            cache_path.unlink()
            return True
        return False

    def clear(self) -> int:
        """Clear all cached files."""
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        logger.info(f"File cache cleared: {count} files")
        return count


class AIResponseCache:
    """
    Specialized cache for AI responses.

    Combines memory and file caching with prompt-based keys.
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize AI response cache.

        Args:
            enabled: Whether caching is enabled
        """
        self.enabled = enabled
        self.memory_cache = MemoryCache(default_ttl=1800)  # 30 min memory cache
        self.file_cache = FileCache(default_ttl=86400)  # 24 hour file cache

        if enabled:
            logger.info("AI response caching enabled")
        else:
            logger.info("AI response caching disabled")

    def _generate_key(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int
    ) -> str:
        """Generate cache key from AI request parameters."""
        key_data = {
            "prompt": prompt,
            "system": system or "",
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> str | None:
        """
        Get cached AI response.

        Args:
            prompt: User prompt
            system: System prompt
            temperature: Temperature used
            max_tokens: Max tokens used

        Returns:
            Cached response or None
        """
        if not self.enabled:
            return None

        key = self._generate_key(prompt, system, temperature, max_tokens)

        # Try memory cache first
        result = self.memory_cache.get(key)
        if result is not None:
            return result

        # Try file cache
        result = self.file_cache.get(key)
        if result is not None:
            # Promote to memory cache
            self.memory_cache.set(key, result)
            return result

        return None

    def set(
        self,
        prompt: str,
        response: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> None:
        """
        Cache an AI response.

        Args:
            prompt: User prompt
            response: AI response
            system: System prompt
            temperature: Temperature used
            max_tokens: Max tokens used
        """
        if not self.enabled:
            return

        key = self._generate_key(prompt, system, temperature, max_tokens)

        # Store in both caches
        self.memory_cache.set(key, response)
        self.file_cache.set(key, response)

    def invalidate_project(self, project_id: str) -> None:
        """
        Invalidate all cache entries for a project.

        Note: This is a simple implementation that clears all caches.
        A production system would use tagged cache entries.
        """
        # For now, just clear memory cache
        # File cache entries will expire naturally
        self.memory_cache.clear()
        logger.info(f"Cache invalidated for project: {project_id}")

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "enabled": self.enabled,
            "memory": self.memory_cache.stats()
        }


# =============================================================================
# Singleton Access
# =============================================================================

_ai_cache: AIResponseCache | None = None


def get_ai_cache() -> AIResponseCache:
    """Get singleton AI response cache."""
    global _ai_cache
    if _ai_cache is None:
        settings = get_settings()
        # Enable caching unless explicitly disabled
        enabled = getattr(settings, 'cache_enabled', True)
        _ai_cache = AIResponseCache(enabled=enabled)
    return _ai_cache
