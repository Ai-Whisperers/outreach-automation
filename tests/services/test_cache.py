"""
Service tests for caching module.

Tests cover:
- CacheEntry expiration
- MemoryCache operations
- FileCache operations
- AIResponseCache combined caching
- Cache statistics
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCacheEntry:
    """Tests for CacheEntry class."""

    def test_cache_entry_creation(self):
        """Test cache entry creation."""
        from api.services.cache import CacheEntry

        entry = CacheEntry(value="test value", ttl_seconds=3600)

        assert entry.value == "test value"
        assert entry.ttl_seconds == 3600
        assert entry.created_at <= time.time()

    def test_cache_entry_not_expired(self):
        """Test entry is not expired before TTL."""
        from api.services.cache import CacheEntry

        entry = CacheEntry(value="test", ttl_seconds=3600)

        assert entry.is_expired() is False

    def test_cache_entry_expired(self):
        """Test entry is expired after TTL."""
        from api.services.cache import CacheEntry

        entry = CacheEntry(value="test", ttl_seconds=1)
        # Manually set created_at to past
        entry.created_at = time.time() - 10

        assert entry.is_expired() is True

    def test_cache_entry_never_expires(self):
        """Test entry with TTL <= 0 never expires."""
        from api.services.cache import CacheEntry

        entry = CacheEntry(value="test", ttl_seconds=0)
        entry.created_at = time.time() - 10000

        assert entry.is_expired() is False

        entry2 = CacheEntry(value="test", ttl_seconds=-1)
        entry2.created_at = time.time() - 10000

        assert entry2.is_expired() is False


class TestMemoryCache:
    """Tests for MemoryCache class."""

    @pytest.fixture
    def cache(self):
        """Create memory cache."""
        from api.services.cache import MemoryCache

        return MemoryCache(default_ttl=3600)

    def test_set_and_get(self, cache):
        """Test basic set and get."""
        cache.set("key1", "value1")

        result = cache.get("key1")

        assert result == "value1"

    def test_get_nonexistent(self, cache):
        """Test get for nonexistent key."""
        result = cache.get("nonexistent")

        assert result is None

    def test_get_expired(self, cache):
        """Test get for expired entry."""
        cache.set("key1", "value1", ttl=1)
        # Manually expire
        cache._cache["key1"].created_at = time.time() - 10

        result = cache.get("key1")

        assert result is None
        assert "key1" not in cache._cache  # Should be deleted

    def test_delete_existing(self, cache):
        """Test delete existing key."""
        cache.set("key1", "value1")

        result = cache.delete("key1")

        assert result is True
        assert cache.get("key1") is None

    def test_delete_nonexistent(self, cache):
        """Test delete nonexistent key."""
        result = cache.delete("nonexistent")

        assert result is False

    def test_clear(self, cache):
        """Test clearing all entries."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        count = cache.clear()

        assert count == 3
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_cleanup_expired(self, cache):
        """Test cleanup of expired entries."""
        cache.set("fresh", "value", ttl=3600)
        cache.set("expired1", "value", ttl=1)
        cache.set("expired2", "value", ttl=1)

        # Manually expire
        cache._cache["expired1"].created_at = time.time() - 10
        cache._cache["expired2"].created_at = time.time() - 10

        count = cache.cleanup_expired()

        assert count == 2
        assert cache.get("fresh") == "value"
        assert cache.get("expired1") is None
        assert cache.get("expired2") is None

    def test_stats(self, cache):
        """Test cache statistics."""
        # Generate some hits and misses
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.stats()

        assert stats["entries"] == 1
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert "hit_rate" in stats

    def test_generate_key(self, cache):
        """Test key generation from arguments."""
        key1 = cache._generate_key("arg1", "arg2", kwarg1="value1")
        key2 = cache._generate_key("arg1", "arg2", kwarg1="value1")
        key3 = cache._generate_key("arg1", "arg2", kwarg1="different")

        assert key1 == key2  # Same args = same key
        assert key1 != key3  # Different args = different key


class TestFileCache:
    """Tests for FileCache class."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create file cache with temp directory."""
        from api.services.cache import FileCache

        cache_dir = tmp_path / "cache"
        return FileCache(cache_dir=cache_dir, default_ttl=3600)

    def test_set_and_get(self, cache):
        """Test basic set and get."""
        cache.set("key1", {"data": "value"})

        result = cache.get("key1")

        assert result == {"data": "value"}

    def test_get_nonexistent(self, cache):
        """Test get for nonexistent key."""
        result = cache.get("nonexistent")

        assert result is None

    def test_get_expired(self, cache, tmp_path):
        """Test get for expired entry."""
        cache.set("key1", "value", ttl=1)

        # Manually modify file to be expired
        cache_file = cache._get_cache_path("key1")
        with open(cache_file) as f:
            data = json.load(f)
        data["created_at"] = time.time() - 10
        with open(cache_file, "w") as f:
            json.dump(data, f)

        result = cache.get("key1")

        assert result is None
        assert not cache_file.exists()  # Should be deleted

    def test_delete_existing(self, cache):
        """Test delete existing key."""
        cache.set("key1", "value")

        result = cache.delete("key1")

        assert result is True
        assert cache.get("key1") is None

    def test_delete_nonexistent(self, cache):
        """Test delete nonexistent key."""
        result = cache.delete("nonexistent")

        assert result is False

    def test_clear(self, cache):
        """Test clearing all entries."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        count = cache.clear()

        assert count == 2
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_path(self, cache):
        """Test cache file path generation."""
        path = cache._get_cache_path("test-key")

        assert path.name == "test-key.json"
        assert path.parent == cache.cache_dir

    def test_creates_cache_dir(self, tmp_path):
        """Test cache directory is created."""
        from api.services.cache import FileCache

        cache_dir = tmp_path / "new_cache_dir"
        assert not cache_dir.exists()

        FileCache(cache_dir=cache_dir)

        assert cache_dir.exists()


class TestAIResponseCache:
    """Tests for AIResponseCache class."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create AI response cache."""
        with patch("api.services.cache.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path
            mock_settings.return_value.cache_enabled = True

            from api.services.cache import AIResponseCache

            return AIResponseCache(enabled=True)

    def test_cache_enabled(self, cache):
        """Test cache is enabled."""
        assert cache.enabled is True

    def test_cache_disabled(self, tmp_path):
        """Test cache when disabled."""
        with patch("api.services.cache.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            from api.services.cache import AIResponseCache

            cache = AIResponseCache(enabled=False)

        assert cache.enabled is False
        assert cache.get("prompt") is None

    def test_set_and_get(self, cache):
        """Test set and get with AI parameters."""
        cache.set(
            prompt="Test prompt",
            response="AI response",
            system="System prompt",
            temperature=0.7,
            max_tokens=4096,
        )

        result = cache.get(
            prompt="Test prompt",
            system="System prompt",
            temperature=0.7,
            max_tokens=4096,
        )

        assert result == "AI response"

    def test_get_miss_different_params(self, cache):
        """Test cache miss with different parameters."""
        cache.set(
            prompt="Test prompt",
            response="Response 1",
            temperature=0.7,
            max_tokens=4096,
        )

        # Different temperature should miss
        result = cache.get(
            prompt="Test prompt",
            temperature=0.5,
            max_tokens=4096,
        )

        assert result is None

    def test_memory_cache_promotion(self, cache):
        """Test file cache hit promotes to memory cache."""
        # Set in both caches
        cache.set(
            prompt="Test",
            response="Response",
            temperature=0.7,
            max_tokens=4096,
        )

        # Clear memory cache only
        cache.memory_cache.clear()

        # Get should find in file cache and promote
        result = cache.get(
            prompt="Test",
            temperature=0.7,
            max_tokens=4096,
        )

        assert result == "Response"
        # Should now be in memory cache
        key = cache._generate_key("Test", None, 0.7, 4096)
        assert cache.memory_cache.get(key) == "Response"

    def test_generate_key(self, cache):
        """Test key generation from AI parameters."""
        key1 = cache._generate_key("prompt", "system", 0.7, 4096)
        key2 = cache._generate_key("prompt", "system", 0.7, 4096)
        key3 = cache._generate_key("prompt", "system", 0.5, 4096)

        assert key1 == key2
        assert key1 != key3

    def test_invalidate_project(self, cache):
        """Test project cache invalidation."""
        cache.set(
            prompt="Test",
            response="Response",
            temperature=0.7,
            max_tokens=4096,
        )

        cache.invalidate_project("test-project")

        # Memory cache should be cleared
        key = cache._generate_key("Test", None, 0.7, 4096)
        assert cache.memory_cache.get(key) is None

    def test_stats(self, cache):
        """Test cache statistics."""
        cache.set(
            prompt="Test",
            response="Response",
            temperature=0.7,
            max_tokens=4096,
        )
        cache.get(prompt="Test", temperature=0.7, max_tokens=4096)

        stats = cache.stats()

        assert stats["enabled"] is True
        assert "memory" in stats

    def test_disabled_cache_no_ops(self, tmp_path):
        """Test disabled cache doesn't store anything."""
        with patch("api.services.cache.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            from api.services.cache import AIResponseCache

            cache = AIResponseCache(enabled=False)

        cache.set(
            prompt="Test",
            response="Response",
            temperature=0.7,
            max_tokens=4096,
        )

        result = cache.get(
            prompt="Test",
            temperature=0.7,
            max_tokens=4096,
        )

        assert result is None


class TestCacheSingleton:
    """Tests for cache singleton access."""

    def test_get_ai_cache_returns_same_instance(self, tmp_path):
        """Test singleton pattern."""
        with patch("api.services.cache.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path
            mock_settings.return_value.cache_enabled = True

            # Reset singleton
            import api.services.cache
            api.services.cache._ai_cache = None

            from api.services.cache import get_ai_cache

            cache1 = get_ai_cache()
            cache2 = get_ai_cache()

            assert cache1 is cache2


class TestCacheEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def memory_cache(self):
        """Create memory cache."""
        from api.services.cache import MemoryCache

        return MemoryCache(default_ttl=3600)

    def test_memory_cache_complex_values(self, memory_cache):
        """Test caching complex data structures."""
        complex_value = {
            "list": [1, 2, 3],
            "nested": {"key": "value"},
            "number": 42,
            "boolean": True,
        }

        memory_cache.set("complex", complex_value)
        result = memory_cache.get("complex")

        assert result == complex_value

    def test_file_cache_handles_corrupted_file(self, tmp_path):
        """Test file cache handles corrupted JSON."""
        from api.services.cache import FileCache

        cache = FileCache(cache_dir=tmp_path)

        # Create corrupted cache file
        cache_file = tmp_path / "corrupted.json"
        cache_file.write_text("not valid json {{{")

        result = cache.get("corrupted")

        assert result is None

    def test_file_cache_handles_missing_fields(self, tmp_path):
        """Test file cache handles missing fields in JSON."""
        from api.services.cache import FileCache

        cache = FileCache(cache_dir=tmp_path)

        # Create cache file with missing fields
        cache_file = tmp_path / "incomplete.json"
        cache_file.write_text('{"value": "test"}')  # Missing created_at and ttl

        result = cache.get("incomplete")

        # Should still work with defaults
        assert result == "test"

    def test_memory_cache_hit_rate_calculation(self, memory_cache):
        """Test hit rate percentage calculation."""
        memory_cache.set("key", "value")

        # 2 hits, 1 miss
        memory_cache.get("key")
        memory_cache.get("key")
        memory_cache.get("nonexistent")

        stats = memory_cache.stats()

        # 2 hits out of 3 requests = 66.7%
        assert "66" in stats["hit_rate"]
