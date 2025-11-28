"""
Outreach Rate Limiter Service.

Redis-based rate limiter for outreach channels with:
- Daily limits per channel
- Per-campaign limits
- Email warmup schedules for new accounts
- Quota tracking and reporting
"""

from datetime import datetime, timedelta
from typing import Any

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger("services.rate_limiter")

# Try to import redis - it's optional
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not installed. Using in-memory rate limiting.")


# =============================================================================
# Constants
# =============================================================================

# Default limits by channel
DEFAULT_LIMITS = {
    "linkedin_connection": 20,  # LinkedIn max is ~25, use 20 for safety
    "linkedin_message": 100,
    "email": 50,
}

# Email warmup schedule (days since account creation -> daily limit)
EMAIL_WARMUP_SCHEDULE = [
    (7, 10),     # Week 1: 10/day
    (14, 20),    # Week 2: 20/day
    (21, 35),    # Week 3: 35/day
    (28, 50),    # Week 4: 50/day
    (float("inf"), 100),  # After: 100/day
]


# =============================================================================
# Rate Limiter
# =============================================================================


class OutreachRateLimiter:
    """
    Token bucket rate limiter using Redis.

    Supports:
    - Daily limits per channel
    - Per-campaign limits
    - Warmup schedules for new email accounts
    """

    def __init__(self, redis_url: str | None = None):
        self.settings = get_settings()
        self.redis_url = redis_url or getattr(
            self.settings, "redis_url", "redis://localhost:6379/0"
        )
        self._redis: redis.Redis | None = None
        self._local_cache: dict[str, int] = {}  # Fallback if Redis unavailable

    async def _get_redis(self) -> redis.Redis | None:
        """Get or create Redis connection."""
        if not REDIS_AVAILABLE:
            return None

        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Test connection
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Using local cache.")
                self._redis = None

        return self._redis

    def _get_key(self, channel: str, campaign_id: int, date: str) -> str:
        """Generate Redis key for quota tracking."""
        return f"outreach:quota:{channel}:{campaign_id}:{date}"

    async def check_quota(
        self,
        channel: str,
        campaign_id: int,
        limit: int | None = None,
    ) -> tuple[bool, int]:
        """
        Check if sending is allowed under quota.

        Args:
            channel: Channel name (linkedin_connection, linkedin_message, email)
            campaign_id: Campaign ID
            limit: Optional custom limit (uses default if not provided)

        Returns:
            (is_allowed, remaining_count)
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = self._get_key(channel, campaign_id, today)

        # Use default limit if not provided
        if limit is None:
            limit = DEFAULT_LIMITS.get(channel, 50)

        r = await self._get_redis()

        try:
            if r:
                current = await r.get(key)
                current = int(current) if current else 0
            else:
                # Fallback to local cache
                current = self._local_cache.get(key, 0)

            remaining = max(0, limit - current)
            is_allowed = current < limit

            logger.debug(
                f"Quota check: {channel}/{campaign_id} - {current}/{limit} "
                f"(allowed: {is_allowed}, remaining: {remaining})"
            )

            return is_allowed, remaining

        except Exception as e:
            logger.error(f"Error checking quota: {e}")
            # Fail open - allow the request
            return True, limit

    async def increment_usage(
        self,
        channel: str,
        campaign_id: int,
        count: int = 1,
    ) -> int:
        """
        Increment usage counter after successful send.

        Args:
            channel: Channel name
            campaign_id: Campaign ID
            count: Number to increment (default 1)

        Returns:
            New total count
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = self._get_key(channel, campaign_id, today)

        r = await self._get_redis()

        try:
            if r:
                new_count = await r.incrby(key, count)

                # Set expiry at end of day + buffer (48 hours)
                await r.expireat(
                    key,
                    int((datetime.utcnow() + timedelta(days=2)).timestamp())
                )

                return new_count
            else:
                # Fallback to local cache
                self._local_cache[key] = self._local_cache.get(key, 0) + count
                return self._local_cache[key]

        except Exception as e:
            logger.error(f"Error incrementing usage: {e}")
            return 0

    async def get_current_usage(
        self,
        channel: str,
        campaign_id: int,
    ) -> int:
        """Get current usage count for today."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = self._get_key(channel, campaign_id, today)

        r = await self._get_redis()

        try:
            if r:
                current = await r.get(key)
                return int(current) if current else 0
            else:
                return self._local_cache.get(key, 0)
        except Exception as e:
            logger.error(f"Error getting usage: {e}")
            return 0

    async def get_quota_status(
        self,
        campaign_id: int,
        limits: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """
        Get full quota status for a campaign.

        Args:
            campaign_id: Campaign ID
            limits: Optional custom limits by channel

        Returns:
            {
                "date": "2024-01-15",
                "channels": {
                    "linkedin_connection": {
                        "used": 5,
                        "limit": 20,
                        "remaining": 15,
                        "percentage": 25
                    },
                    ...
                }
            }
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        limits = limits or DEFAULT_LIMITS

        status = {
            "date": today,
            "campaign_id": campaign_id,
            "channels": {},
        }

        for channel, limit in limits.items():
            used = await self.get_current_usage(channel, campaign_id)
            remaining = max(0, limit - used)
            percentage = int((used / limit) * 100) if limit > 0 else 0

            status["channels"][channel] = {
                "used": used,
                "limit": limit,
                "remaining": remaining,
                "percentage": percentage,
            }

        return status

    # =========================================================================
    # Email Warmup
    # =========================================================================

    def get_warmup_limit(
        self,
        account_age_days: int,
        base_limit: int = 100,
    ) -> int:
        """
        Get warmup-adjusted limit for email accounts.

        New email sending accounts need gradual volume increase
        to build reputation and avoid spam filters.

        Args:
            account_age_days: Days since account/domain was set up
            base_limit: Maximum limit after warmup

        Returns:
            Adjusted daily limit
        """
        for day_threshold, warmup_limit in EMAIL_WARMUP_SCHEDULE:
            if account_age_days < day_threshold:
                return min(warmup_limit, base_limit)

        return base_limit

    async def check_email_quota_with_warmup(
        self,
        campaign_id: int,
        account_age_days: int,
        base_limit: int = 100,
    ) -> tuple[bool, int]:
        """
        Check email quota with warmup schedule applied.

        Args:
            campaign_id: Campaign ID
            account_age_days: Days since email account setup
            base_limit: Maximum limit after warmup

        Returns:
            (is_allowed, remaining_count)
        """
        adjusted_limit = self.get_warmup_limit(account_age_days, base_limit)
        return await self.check_quota("email", campaign_id, adjusted_limit)

    # =========================================================================
    # Optimal Timing
    # =========================================================================

    def get_optimal_send_window(
        self,
        timezone: str = "UTC",
        channel: str = "email",
    ) -> tuple[int, int]:
        """
        Get optimal hours for sending based on engagement data.

        Args:
            timezone: Target timezone
            channel: Channel (email or linkedin)

        Returns:
            (start_hour, end_hour) in 24h format

        Note: This is a static implementation. Could be enhanced with
        ML based on actual engagement data.
        """
        # Best times based on industry research
        optimal_times = {
            "email": {
                "start": 9,   # 9 AM
                "end": 17,    # 5 PM
                "peaks": [10, 14],  # 10 AM and 2 PM are best
            },
            "linkedin_connection": {
                "start": 8,   # 8 AM
                "end": 18,    # 6 PM
                "peaks": [9, 12, 17],  # Morning, lunch, end of day
            },
            "linkedin_message": {
                "start": 8,
                "end": 18,
                "peaks": [9, 14],
            },
        }

        config = optimal_times.get(channel, optimal_times["email"])
        return config["start"], config["end"]

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def clear_campaign_quota(self, campaign_id: int):
        """Clear all quota data for a campaign (for testing)."""
        today = datetime.utcnow().strftime("%Y-%m-%d")

        r = await self._get_redis()

        if r:
            for channel in DEFAULT_LIMITS.keys():
                key = self._get_key(channel, campaign_id, today)
                await r.delete(key)
        else:
            for channel in DEFAULT_LIMITS.keys():
                key = self._get_key(channel, campaign_id, today)
                self._local_cache.pop(key, None)


# =============================================================================
# Singleton Instance
# =============================================================================

_rate_limiter: OutreachRateLimiter | None = None


def get_outreach_rate_limiter() -> OutreachRateLimiter:
    """Get singleton OutreachRateLimiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = OutreachRateLimiter()
    return _rate_limiter


async def get_rate_limiter_async() -> OutreachRateLimiter:
    """Async factory for dependency injection."""
    return get_outreach_rate_limiter()
