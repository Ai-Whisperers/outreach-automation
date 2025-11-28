"""
Integration tests for OutreachRateLimiter service.

Tests cover:
- Quota checking
- Usage incrementing
- Warmup schedules
- Optimal send windows
- Local cache fallback (when Redis unavailable)
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from api.services.outreach_rate_limiter import (
    DEFAULT_LIMITS,
    EMAIL_WARMUP_SCHEDULE,
    OutreachRateLimiter,
    get_outreach_rate_limiter,
)


class TestRateLimiterFactory:
    """Test factory functions."""

    def test_get_outreach_rate_limiter(self):
        """Test factory returns singleton instance."""
        limiter1 = get_outreach_rate_limiter()
        limiter2 = get_outreach_rate_limiter()

        assert limiter1 is limiter2

    def test_rate_limiter_instance(self):
        """Test RateLimiter can be instantiated."""
        limiter = OutreachRateLimiter()

        assert limiter is not None
        assert limiter._local_cache == {}


class TestLocalCacheFallback:
    """Tests for local cache when Redis is unavailable."""

    @pytest_asyncio.fixture
    async def limiter(self):
        """Create limiter without Redis."""
        limiter = OutreachRateLimiter(redis_url="redis://invalid:6379")
        limiter._redis = None  # Ensure Redis is not connected
        yield limiter
        await limiter.close()

    @pytest.mark.asyncio
    async def test_check_quota_local_cache(self, limiter):
        """Test quota check with local cache."""
        is_allowed, remaining = await limiter.check_quota(
            channel="email",
            campaign_id=1,
            limit=50,
        )

        assert is_allowed is True
        assert remaining == 50

    @pytest.mark.asyncio
    async def test_increment_usage_local_cache(self, limiter):
        """Test incrementing usage with local cache."""
        new_count = await limiter.increment_usage(
            channel="email",
            campaign_id=1,
            count=5,
        )

        assert new_count == 5

        # Increment again
        new_count = await limiter.increment_usage(
            channel="email",
            campaign_id=1,
            count=3,
        )

        assert new_count == 8

    @pytest.mark.asyncio
    async def test_get_current_usage_local_cache(self, limiter):
        """Test getting current usage with local cache."""
        # Initially zero
        usage = await limiter.get_current_usage(
            channel="email",
            campaign_id=1,
        )
        assert usage == 0

        # After incrementing
        await limiter.increment_usage(channel="email", campaign_id=1, count=10)

        usage = await limiter.get_current_usage(
            channel="email",
            campaign_id=1,
        )
        assert usage == 10

    @pytest.mark.asyncio
    async def test_quota_enforcement_local_cache(self, limiter):
        """Test quota enforcement with local cache."""
        # Use up quota
        for _ in range(20):
            await limiter.increment_usage(
                channel="linkedin_connection",
                campaign_id=1,
                count=1,
            )

        # Check quota - should be denied
        is_allowed, remaining = await limiter.check_quota(
            channel="linkedin_connection",
            campaign_id=1,
            limit=20,
        )

        assert is_allowed is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_get_quota_status_local_cache(self, limiter):
        """Test getting full quota status with local cache."""
        # Set some usage
        await limiter.increment_usage(channel="email", campaign_id=1, count=10)
        await limiter.increment_usage(channel="linkedin_connection", campaign_id=1, count=5)

        status = await limiter.get_quota_status(campaign_id=1)

        assert status["date"] == datetime.utcnow().strftime("%Y-%m-%d")
        assert status["campaign_id"] == 1
        assert "channels" in status

    @pytest.mark.asyncio
    async def test_clear_campaign_quota_local_cache(self, limiter):
        """Test clearing campaign quota with local cache."""
        # Set some usage
        await limiter.increment_usage(channel="email", campaign_id=1, count=10)

        # Clear
        await limiter.clear_campaign_quota(campaign_id=1)

        # Verify cleared
        usage = await limiter.get_current_usage(channel="email", campaign_id=1)
        assert usage == 0


class TestDefaultLimits:
    """Tests for default limit values."""

    def test_default_limits_defined(self):
        """Test default limits are defined."""
        assert "linkedin_connection" in DEFAULT_LIMITS
        assert "linkedin_message" in DEFAULT_LIMITS
        assert "email" in DEFAULT_LIMITS

    def test_linkedin_connection_limit(self):
        """Test LinkedIn connection limit is conservative."""
        assert DEFAULT_LIMITS["linkedin_connection"] == 20  # Safety margin below 25

    def test_email_limit(self):
        """Test email limit."""
        assert DEFAULT_LIMITS["email"] == 50


class TestWarmupSchedule:
    """Tests for email warmup schedule."""

    @pytest_asyncio.fixture
    async def limiter(self):
        limiter = OutreachRateLimiter()
        limiter._redis = None
        yield limiter
        await limiter.close()

    def test_warmup_schedule_defined(self):
        """Test warmup schedule is properly defined."""
        assert len(EMAIL_WARMUP_SCHEDULE) > 0

        # Should be ascending day thresholds
        prev_days = 0
        for days, limit in EMAIL_WARMUP_SCHEDULE:
            assert days >= prev_days
            assert limit > 0
            prev_days = days

    def test_get_warmup_limit_week1(self, limiter):
        """Test warmup limit in week 1."""
        limit = limiter.get_warmup_limit(account_age_days=3)

        assert limit == 10  # Week 1 limit

    def test_get_warmup_limit_week2(self, limiter):
        """Test warmup limit in week 2."""
        limit = limiter.get_warmup_limit(account_age_days=10)

        assert limit == 20  # Week 2 limit

    def test_get_warmup_limit_week3(self, limiter):
        """Test warmup limit in week 3."""
        limit = limiter.get_warmup_limit(account_age_days=18)

        assert limit == 35  # Week 3 limit

    def test_get_warmup_limit_week4(self, limiter):
        """Test warmup limit in week 4."""
        limit = limiter.get_warmup_limit(account_age_days=25)

        assert limit == 50  # Week 4 limit

    def test_get_warmup_limit_after_warmup(self, limiter):
        """Test warmup limit after warmup period."""
        limit = limiter.get_warmup_limit(account_age_days=60)

        assert limit == 100  # Full limit

    def test_get_warmup_limit_respects_base_limit(self, limiter):
        """Test warmup limit respects base limit."""
        # Even after warmup, should not exceed base limit
        limit = limiter.get_warmup_limit(account_age_days=60, base_limit=50)

        assert limit == 50  # Capped at base limit

    @pytest.mark.asyncio
    async def test_check_email_quota_with_warmup(self, limiter):
        """Test email quota check with warmup applied."""
        is_allowed, remaining = await limiter.check_email_quota_with_warmup(
            campaign_id=1,
            account_age_days=5,  # Week 1
            base_limit=100,
        )

        assert is_allowed is True
        assert remaining == 10  # Week 1 limit


class TestOptimalSendWindows:
    """Tests for optimal send window calculation."""

    @pytest_asyncio.fixture
    async def limiter(self):
        limiter = OutreachRateLimiter()
        yield limiter
        await limiter.close()

    def test_email_optimal_window(self, limiter):
        """Test optimal email send window."""
        start, end = limiter.get_optimal_send_window(channel="email")

        assert start == 9  # 9 AM
        assert end == 17  # 5 PM

    def test_linkedin_connection_optimal_window(self, limiter):
        """Test optimal LinkedIn connection send window."""
        start, end = limiter.get_optimal_send_window(channel="linkedin_connection")

        assert start == 8  # 8 AM
        assert end == 18  # 6 PM

    def test_linkedin_message_optimal_window(self, limiter):
        """Test optimal LinkedIn message send window."""
        start, end = limiter.get_optimal_send_window(channel="linkedin_message")

        assert start == 8
        assert end == 18

    def test_unknown_channel_defaults_to_email(self, limiter):
        """Test unknown channel defaults to email window."""
        start, end = limiter.get_optimal_send_window(channel="unknown")

        assert start == 9
        assert end == 17


class TestKeyGeneration:
    """Tests for Redis key generation."""

    @pytest_asyncio.fixture
    async def limiter(self):
        limiter = OutreachRateLimiter()
        yield limiter
        await limiter.close()

    def test_key_format(self, limiter):
        """Test Redis key format."""
        key = limiter._get_key("email", 123, "2024-01-15")

        assert key == "outreach:quota:email:123:2024-01-15"

    def test_key_with_different_channels(self, limiter):
        """Test keys for different channels."""
        email_key = limiter._get_key("email", 1, "2024-01-15")
        linkedin_key = limiter._get_key("linkedin_connection", 1, "2024-01-15")

        assert email_key != linkedin_key
        assert "email" in email_key
        assert "linkedin_connection" in linkedin_key

    def test_key_with_different_campaigns(self, limiter):
        """Test keys for different campaigns."""
        key1 = limiter._get_key("email", 1, "2024-01-15")
        key2 = limiter._get_key("email", 2, "2024-01-15")

        assert key1 != key2

    def test_key_with_different_dates(self, limiter):
        """Test keys for different dates."""
        key1 = limiter._get_key("email", 1, "2024-01-15")
        key2 = limiter._get_key("email", 1, "2024-01-16")

        assert key1 != key2


class TestQuotaStatus:
    """Tests for quota status reporting."""

    @pytest_asyncio.fixture
    async def limiter(self):
        limiter = OutreachRateLimiter()
        limiter._redis = None
        yield limiter
        await limiter.close()

    @pytest.mark.asyncio
    async def test_quota_status_structure(self, limiter):
        """Test quota status response structure."""
        status = await limiter.get_quota_status(campaign_id=1)

        assert "date" in status
        assert "campaign_id" in status
        assert "channels" in status

    @pytest.mark.asyncio
    async def test_quota_status_channel_details(self, limiter):
        """Test quota status includes channel details."""
        await limiter.increment_usage("email", 1, 15)

        status = await limiter.get_quota_status(campaign_id=1)

        assert "email" in status["channels"]
        channel_status = status["channels"]["email"]

        assert "used" in channel_status
        assert "limit" in channel_status
        assert "remaining" in channel_status
        assert "percentage" in channel_status

    @pytest.mark.asyncio
    async def test_quota_status_percentage_calculation(self, limiter):
        """Test quota percentage is calculated correctly."""
        await limiter.increment_usage("email", 1, 25)

        status = await limiter.get_quota_status(
            campaign_id=1,
            limits={"email": 50},
        )

        email_status = status["channels"]["email"]
        assert email_status["used"] == 25
        assert email_status["limit"] == 50
        assert email_status["remaining"] == 25
        assert email_status["percentage"] == 50

    @pytest.mark.asyncio
    async def test_quota_status_custom_limits(self, limiter):
        """Test quota status with custom limits."""
        custom_limits = {
            "email": 100,
            "linkedin_connection": 30,
        }

        status = await limiter.get_quota_status(
            campaign_id=1,
            limits=custom_limits,
        )

        assert status["channels"]["email"]["limit"] == 100
        assert status["channels"]["linkedin_connection"]["limit"] == 30


class TestErrorHandling:
    """Tests for error handling."""

    @pytest_asyncio.fixture
    async def limiter(self):
        limiter = OutreachRateLimiter()
        limiter._redis = None
        yield limiter
        await limiter.close()

    @pytest.mark.asyncio
    async def test_check_quota_fails_open(self, limiter):
        """Test quota check fails open on error."""
        # Mock an error
        with patch.object(limiter, "_local_cache", new_callable=lambda: MagicMock(
            get=MagicMock(side_effect=Exception("Test error"))
        )):
            is_allowed, remaining = await limiter.check_quota(
                channel="email",
                campaign_id=1,
                limit=50,
            )

            # Should fail open
            assert is_allowed is True
            assert remaining == 50

    @pytest.mark.asyncio
    async def test_increment_returns_zero_on_error(self, limiter):
        """Test increment returns zero on error."""
        # Mock an error
        with patch.object(limiter, "_local_cache", new_callable=lambda: MagicMock(
            get=MagicMock(side_effect=Exception("Test error"))
        )):
            count = await limiter.increment_usage(
                channel="email",
                campaign_id=1,
            )

            assert count == 0

    @pytest.mark.asyncio
    async def test_get_usage_returns_zero_on_error(self, limiter):
        """Test get usage returns zero on error."""
        # Mock an error
        with patch.object(limiter, "_local_cache", new_callable=lambda: MagicMock(
            get=MagicMock(side_effect=Exception("Test error"))
        )):
            usage = await limiter.get_current_usage(
                channel="email",
                campaign_id=1,
            )

            assert usage == 0


class TestMultipleChannels:
    """Tests for handling multiple channels."""

    @pytest_asyncio.fixture
    async def limiter(self):
        limiter = OutreachRateLimiter()
        limiter._redis = None
        yield limiter
        await limiter.close()

    @pytest.mark.asyncio
    async def test_independent_channel_quotas(self, limiter):
        """Test channels have independent quotas."""
        await limiter.increment_usage("email", 1, 30)
        await limiter.increment_usage("linkedin_connection", 1, 10)

        email_usage = await limiter.get_current_usage("email", 1)
        linkedin_usage = await limiter.get_current_usage("linkedin_connection", 1)

        assert email_usage == 30
        assert linkedin_usage == 10

    @pytest.mark.asyncio
    async def test_independent_campaign_quotas(self, limiter):
        """Test campaigns have independent quotas."""
        await limiter.increment_usage("email", 1, 20)
        await limiter.increment_usage("email", 2, 35)

        campaign1_usage = await limiter.get_current_usage("email", 1)
        campaign2_usage = await limiter.get_current_usage("email", 2)

        assert campaign1_usage == 20
        assert campaign2_usage == 35

    @pytest.mark.asyncio
    async def test_clear_only_affects_target_campaign(self, limiter):
        """Test clearing quota only affects target campaign."""
        await limiter.increment_usage("email", 1, 20)
        await limiter.increment_usage("email", 2, 35)

        await limiter.clear_campaign_quota(1)

        campaign1_usage = await limiter.get_current_usage("email", 1)
        campaign2_usage = await limiter.get_current_usage("email", 2)

        assert campaign1_usage == 0
        assert campaign2_usage == 35
