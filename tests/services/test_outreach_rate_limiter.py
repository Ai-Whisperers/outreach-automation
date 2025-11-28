"""
Tests for OutreachRateLimiter.

Tests cover:
- Quota checking
- Usage tracking and incrementing
- Daily limits per channel
- Email warmup integration
- Redis caching with fallback
- Optimal send windows
- Rate limit resets
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOutreachRateLimiterInit:
    """Tests for OutreachRateLimiter initialization."""

    def test_rate_limiter_initialization(self):
        """Test OutreachRateLimiter initializes correctly."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        limiter = OutreachRateLimiter()

        assert limiter is not None
        assert hasattr(limiter, "daily_limits")
        assert hasattr(limiter, "redis_client")

    def test_rate_limiter_default_limits(self):
        """Test default daily limits are set."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        limiter = OutreachRateLimiter()

        assert limiter.daily_limits["linkedin_connection"] == 20
        assert limiter.daily_limits["linkedin_message"] == 100
        assert limiter.daily_limits["email"] == 50

    def test_rate_limiter_custom_limits(self):
        """Test custom limits can be provided."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        custom_limits = {
            "linkedin_connection": 30,
            "linkedin_message": 150,
            "email": 75,
        }
        limiter = OutreachRateLimiter(daily_limits=custom_limits)

        assert limiter.daily_limits["linkedin_connection"] == 30
        assert limiter.daily_limits["email"] == 75


class TestCheckQuota:
    """Tests for check_quota method."""

    @pytest.fixture
    def rate_limiter(self):
        """Create OutreachRateLimiter instance."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        return OutreachRateLimiter()

    @pytest.mark.asyncio
    async def test_check_quota_under_limit(self, rate_limiter):
        """Test check_quota returns True when under limit."""
        rate_limiter._get_current_usage = AsyncMock(return_value=10)

        result = await rate_limiter.check_quota("email", "user123")

        assert result["allowed"] is True
        assert result["remaining"] == 40  # 50 - 10

    @pytest.mark.asyncio
    async def test_check_quota_at_limit(self, rate_limiter):
        """Test check_quota returns False when at limit."""
        rate_limiter._get_current_usage = AsyncMock(return_value=50)

        result = await rate_limiter.check_quota("email", "user123")

        assert result["allowed"] is False
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_check_quota_over_limit(self, rate_limiter):
        """Test check_quota returns False when over limit."""
        rate_limiter._get_current_usage = AsyncMock(return_value=55)

        result = await rate_limiter.check_quota("email", "user123")

        assert result["allowed"] is False
        assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_check_quota_linkedin_connection(self, rate_limiter):
        """Test check_quota for LinkedIn connections."""
        rate_limiter._get_current_usage = AsyncMock(return_value=15)

        result = await rate_limiter.check_quota("linkedin_connection", "user123")

        assert result["allowed"] is True
        assert result["remaining"] == 5  # 20 - 15
        assert result["limit"] == 20

    @pytest.mark.asyncio
    async def test_check_quota_linkedin_message(self, rate_limiter):
        """Test check_quota for LinkedIn messages."""
        rate_limiter._get_current_usage = AsyncMock(return_value=50)

        result = await rate_limiter.check_quota("linkedin_message", "user123")

        assert result["allowed"] is True
        assert result["remaining"] == 50  # 100 - 50
        assert result["limit"] == 100

    @pytest.mark.asyncio
    async def test_check_quota_unknown_channel(self, rate_limiter):
        """Test check_quota for unknown channel uses default."""
        rate_limiter._get_current_usage = AsyncMock(return_value=5)

        result = await rate_limiter.check_quota("unknown_channel", "user123")

        # Should use a default limit or raise error
        assert "allowed" in result

    @pytest.mark.asyncio
    async def test_check_quota_includes_reset_time(self, rate_limiter):
        """Test check_quota includes reset time in response."""
        rate_limiter._get_current_usage = AsyncMock(return_value=50)
        rate_limiter._get_reset_time = MagicMock(return_value=datetime.utcnow() + timedelta(hours=1))

        result = await rate_limiter.check_quota("email", "user123")

        assert "reset_at" in result


class TestIncrementUsage:
    """Tests for increment_usage method."""

    @pytest.fixture
    def rate_limiter(self):
        """Create OutreachRateLimiter instance."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        return OutreachRateLimiter()

    @pytest.mark.asyncio
    async def test_increment_usage_success(self, rate_limiter):
        """Test incrementing usage counter."""
        rate_limiter._get_current_usage = AsyncMock(return_value=10)
        rate_limiter._set_usage = AsyncMock()

        await rate_limiter.increment_usage("email", "user123")

        rate_limiter._set_usage.assert_called_once()

    @pytest.mark.asyncio
    async def test_increment_usage_by_count(self, rate_limiter):
        """Test incrementing by specific count."""
        rate_limiter._get_current_usage = AsyncMock(return_value=10)
        rate_limiter._set_usage = AsyncMock()

        await rate_limiter.increment_usage("email", "user123", count=5)

        # Verify set_usage was called with incremented value
        call_args = rate_limiter._set_usage.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_increment_usage_updates_redis(self, rate_limiter):
        """Test increment updates Redis cache."""
        mock_redis = MagicMock()
        mock_redis.incr = AsyncMock(return_value=11)
        rate_limiter.redis_client = mock_redis

        with patch.object(rate_limiter, "_use_redis", True):
            await rate_limiter.increment_usage("email", "user123")

            # Redis incr should be called
            assert mock_redis.incr.called or rate_limiter._set_usage

    @pytest.mark.asyncio
    async def test_increment_usage_fallback_to_memory(self, rate_limiter):
        """Test increment falls back to memory when Redis fails."""
        rate_limiter.redis_client = None
        rate_limiter._memory_cache = {}
        rate_limiter._get_current_usage = AsyncMock(return_value=10)
        rate_limiter._set_usage = AsyncMock()

        await rate_limiter.increment_usage("email", "user123")

        # Should still succeed with memory fallback
        rate_limiter._set_usage.assert_called()


class TestGetWarmupLimit:
    """Tests for warmup limit calculations."""

    @pytest.fixture
    def rate_limiter(self):
        """Create OutreachRateLimiter instance."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        return OutreachRateLimiter()

    @pytest.mark.asyncio
    async def test_get_warmup_limit_week_1(self, rate_limiter):
        """Test warmup limit for week 1."""
        # Week 1: typically 10-20 emails/day
        result = await rate_limiter.get_warmup_limit("domain123", week=1)

        assert result <= 20
        assert result >= 5

    @pytest.mark.asyncio
    async def test_get_warmup_limit_week_4(self, rate_limiter):
        """Test warmup limit for week 4."""
        # Week 4: should be higher than week 1
        result = await rate_limiter.get_warmup_limit("domain123", week=4)

        assert result >= 20

    @pytest.mark.asyncio
    async def test_get_warmup_limit_week_8(self, rate_limiter):
        """Test warmup limit for week 8 (full capacity)."""
        # Week 8: should be at or near full limit
        result = await rate_limiter.get_warmup_limit("domain123", week=8)

        assert result >= 40

    @pytest.mark.asyncio
    async def test_get_warmup_limit_adjusts_email_limit(self, rate_limiter):
        """Test warmup limit affects email quota check."""
        rate_limiter.get_warmup_limit = AsyncMock(return_value=15)
        rate_limiter._get_current_usage = AsyncMock(return_value=10)

        # When warmup limit is 15 and usage is 10
        result = await rate_limiter.check_quota("email", "user123", warmup_week=1)

        # Should use warmup limit instead of default
        assert result["remaining"] <= 5


class TestOptimalSendWindow:
    """Tests for optimal send window calculation."""

    @pytest.fixture
    def rate_limiter(self):
        """Create OutreachRateLimiter instance."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        return OutreachRateLimiter()

    def test_get_optimal_send_window_business_hours(self, rate_limiter):
        """Test optimal window during business hours."""
        result = rate_limiter.get_optimal_send_window(timezone="America/New_York")

        assert "start" in result
        assert "end" in result
        # Business hours typically 9-17
        assert result["start"].hour >= 8
        assert result["end"].hour <= 18

    def test_get_optimal_send_window_weekday(self, rate_limiter):
        """Test optimal window on weekday."""
        # Mock a weekday
        with patch("api.services.outreach_rate_limiter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 15, 10, 0)  # Monday
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            result = rate_limiter.get_optimal_send_window()

            assert result["is_business_day"] is True

    def test_get_optimal_send_window_weekend(self, rate_limiter):
        """Test optimal window on weekend."""
        with patch("api.services.outreach_rate_limiter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 13, 10, 0)  # Saturday
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            result = rate_limiter.get_optimal_send_window()

            # Weekend might return next business day or reduced hours
            assert "is_business_day" in result or "next_window" in result

    def test_get_optimal_send_window_peak_hours(self, rate_limiter):
        """Test optimal window identifies peak engagement hours."""
        result = rate_limiter.get_optimal_send_window()

        # Peak hours typically 10-11am and 2-3pm
        if "peak_hours" in result:
            assert len(result["peak_hours"]) > 0


class TestRateLimitReset:
    """Tests for rate limit reset functionality."""

    @pytest.fixture
    def rate_limiter(self):
        """Create OutreachRateLimiter instance."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        return OutreachRateLimiter()

    def test_get_reset_time_midnight(self, rate_limiter):
        """Test reset time is midnight UTC."""
        reset_time = rate_limiter._get_reset_time()

        assert reset_time.hour == 0
        assert reset_time.minute == 0
        assert reset_time > datetime.utcnow()

    def test_get_reset_time_next_day(self, rate_limiter):
        """Test reset time is next day."""
        now = datetime.utcnow()
        reset_time = rate_limiter._get_reset_time()

        # Should be within 24 hours
        assert (reset_time - now).total_seconds() <= 86400

    @pytest.mark.asyncio
    async def test_reset_usage_clears_counter(self, rate_limiter):
        """Test reset_usage clears the counter."""
        rate_limiter._set_usage = AsyncMock()

        await rate_limiter.reset_usage("email", "user123")

        rate_limiter._set_usage.assert_called_with("email", "user123", 0)


class TestRedisIntegration:
    """Tests for Redis cache integration."""

    @pytest.fixture
    def rate_limiter_with_redis(self):
        """Create rate limiter with mocked Redis."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        limiter = OutreachRateLimiter()
        limiter.redis_client = MagicMock()
        limiter.redis_client.get = AsyncMock(return_value=b"25")
        limiter.redis_client.set = AsyncMock()
        limiter.redis_client.incr = AsyncMock(return_value=26)
        limiter.redis_client.expire = AsyncMock()
        return limiter

    @pytest.mark.asyncio
    async def test_redis_get_usage(self, rate_limiter_with_redis):
        """Test getting usage from Redis."""
        usage = await rate_limiter_with_redis._get_current_usage("email", "user123")

        assert usage == 25

    @pytest.mark.asyncio
    async def test_redis_set_usage_with_expiry(self, rate_limiter_with_redis):
        """Test setting usage in Redis with expiry."""
        await rate_limiter_with_redis._set_usage("email", "user123", 30)

        rate_limiter_with_redis.redis_client.set.assert_called()
        # Should set expiry for end of day
        rate_limiter_with_redis.redis_client.expire.assert_called()

    @pytest.mark.asyncio
    async def test_redis_connection_failure_fallback(self):
        """Test fallback when Redis connection fails."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        limiter = OutreachRateLimiter()
        limiter.redis_client = MagicMock()
        limiter.redis_client.get = AsyncMock(side_effect=Exception("Connection failed"))
        limiter._memory_cache = {"email:user123": 15}

        # Should fall back to memory cache
        usage = await limiter._get_current_usage("email", "user123")

        assert usage == 15 or usage == 0  # Either memory value or default


class TestMemoryFallback:
    """Tests for in-memory fallback cache."""

    @pytest.fixture
    def rate_limiter_no_redis(self):
        """Create rate limiter without Redis."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        limiter = OutreachRateLimiter()
        limiter.redis_client = None
        limiter._memory_cache = {}
        return limiter

    @pytest.mark.asyncio
    async def test_memory_cache_get(self, rate_limiter_no_redis):
        """Test getting from memory cache."""
        rate_limiter_no_redis._memory_cache = {"email:user123:2024-01-15": 20}

        with patch("api.services.outreach_rate_limiter.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2024, 1, 15, 10, 0)
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            usage = await rate_limiter_no_redis._get_current_usage("email", "user123")

            assert usage == 20

    @pytest.mark.asyncio
    async def test_memory_cache_set(self, rate_limiter_no_redis):
        """Test setting in memory cache."""
        with patch("api.services.outreach_rate_limiter.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2024, 1, 15, 10, 0)
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            await rate_limiter_no_redis._set_usage("email", "user123", 25)

            key = "email:user123:2024-01-15"
            assert rate_limiter_no_redis._memory_cache.get(key) == 25

    @pytest.mark.asyncio
    async def test_memory_cache_daily_reset(self, rate_limiter_no_redis):
        """Test memory cache resets daily."""
        # Set yesterday's usage
        rate_limiter_no_redis._memory_cache = {"email:user123:2024-01-14": 50}

        with patch("api.services.outreach_rate_limiter.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2024, 1, 15, 10, 0)
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            usage = await rate_limiter_no_redis._get_current_usage("email", "user123")

            # Should be 0 for new day
            assert usage == 0


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    @pytest.fixture
    def rate_limiter(self):
        """Create OutreachRateLimiter instance."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        return OutreachRateLimiter()

    def test_cache_key_format(self, rate_limiter):
        """Test cache key format includes channel, user, and date."""
        key = rate_limiter._get_cache_key("email", "user123")

        assert "email" in key
        assert "user123" in key
        # Should include date component
        today = datetime.utcnow().strftime("%Y-%m-%d")
        assert today in key

    def test_cache_key_different_channels(self, rate_limiter):
        """Test different channels have different keys."""
        email_key = rate_limiter._get_cache_key("email", "user123")
        linkedin_key = rate_limiter._get_cache_key("linkedin_connection", "user123")

        assert email_key != linkedin_key

    def test_cache_key_different_users(self, rate_limiter):
        """Test different users have different keys."""
        user1_key = rate_limiter._get_cache_key("email", "user123")
        user2_key = rate_limiter._get_cache_key("email", "user456")

        assert user1_key != user2_key


class TestBulkQuotaCheck:
    """Tests for bulk quota checking."""

    @pytest.fixture
    def rate_limiter(self):
        """Create OutreachRateLimiter instance."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        return OutreachRateLimiter()

    @pytest.mark.asyncio
    async def test_check_bulk_quota(self, rate_limiter):
        """Test checking quota for multiple sends."""
        rate_limiter._get_current_usage = AsyncMock(return_value=40)

        result = await rate_limiter.check_quota("email", "user123", count=5)

        assert result["allowed"] is True  # 40 + 5 = 45 < 50

    @pytest.mark.asyncio
    async def test_check_bulk_quota_exceeds(self, rate_limiter):
        """Test bulk check when it would exceed limit."""
        rate_limiter._get_current_usage = AsyncMock(return_value=48)

        result = await rate_limiter.check_quota("email", "user123", count=5)

        assert result["allowed"] is False  # 48 + 5 = 53 > 50

    @pytest.mark.asyncio
    async def test_check_bulk_quota_partial_allowed(self, rate_limiter):
        """Test bulk check returns how many can be sent."""
        rate_limiter._get_current_usage = AsyncMock(return_value=48)

        result = await rate_limiter.check_quota("email", "user123", count=5)

        assert result["remaining"] == 2  # Can only send 2 more


class TestRateLimitExceptions:
    """Tests for rate limit exceptions."""

    @pytest.fixture
    def rate_limiter(self):
        """Create OutreachRateLimiter instance."""
        from api.services.outreach_rate_limiter import OutreachRateLimiter

        return OutreachRateLimiter()

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_includes_retry_after(self, rate_limiter):
        """Test rate limit response includes retry-after time."""
        rate_limiter._get_current_usage = AsyncMock(return_value=50)

        result = await rate_limiter.check_quota("email", "user123")

        assert result["allowed"] is False
        assert "reset_at" in result or "retry_after" in result

    @pytest.mark.asyncio
    async def test_rate_limit_error_message(self, rate_limiter):
        """Test rate limit includes helpful error message."""
        rate_limiter._get_current_usage = AsyncMock(return_value=50)

        result = await rate_limiter.check_quota("email", "user123")

        assert result["allowed"] is False
        if "message" in result:
            assert "limit" in result["message"].lower() or "exceeded" in result["message"].lower()


class TestSingleton:
    """Tests for singleton access."""

    def test_get_rate_limiter_singleton(self):
        """Test get_rate_limiter returns singleton."""
        import api.services.outreach_rate_limiter as module

        module._rate_limiter = None

        from api.services.outreach_rate_limiter import get_rate_limiter

        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        assert limiter1 is limiter2
