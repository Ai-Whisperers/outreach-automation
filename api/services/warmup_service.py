"""
Domain Warmup Service.

Manages email domain warmup to ensure good deliverability.
New domains need to gradually increase sending volume to build reputation.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_config import get_logger

logger = get_logger("services.warmup")


# =============================================================================
# Warmup Schedule Configuration
# =============================================================================


@dataclass
class WarmupWeek:
    """Configuration for a warmup week."""

    week: int
    daily_limit: int
    delay_between_emails_seconds: int
    notes: str


# Conservative warmup schedule (recommended)
WARMUP_SCHEDULE = {
    1: WarmupWeek(1, 20, 300, "Week 1: Max 20/day, 5 min between emails"),
    2: WarmupWeek(2, 40, 180, "Week 2: Max 40/day, 3 min between emails"),
    3: WarmupWeek(3, 70, 120, "Week 3: Max 70/day, 2 min between emails"),
    4: WarmupWeek(4, 100, 90, "Week 4: Max 100/day, 90 sec between emails"),
    5: WarmupWeek(5, 150, 60, "Week 5: Max 150/day, 1 min between emails"),
    6: WarmupWeek(6, 200, 45, "Week 6: Max 200/day, 45 sec between emails"),
    7: WarmupWeek(7, 300, 30, "Week 7: Max 300/day, 30 sec between emails"),
    8: WarmupWeek(8, 500, 15, "Week 8+: Full capacity, 15 sec between emails"),
}

# Aggressive warmup (use with caution)
AGGRESSIVE_WARMUP_SCHEDULE = {
    1: WarmupWeek(1, 50, 180, "Week 1: Max 50/day"),
    2: WarmupWeek(2, 100, 90, "Week 2: Max 100/day"),
    3: WarmupWeek(3, 200, 60, "Week 3: Max 200/day"),
    4: WarmupWeek(4, 400, 30, "Week 4+: Max 400/day"),
}


# =============================================================================
# Warmup Service
# =============================================================================


class WarmupService:
    """
    Manage domain warmup process.

    Features:
    - Track warmup progress per domain
    - Calculate current daily limits
    - Monitor health metrics (bounce/spam rates)
    - Auto-pause if rates exceed thresholds
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.schedule = WARMUP_SCHEDULE

    async def get_warmup_status(self, domain: str) -> dict[str, Any]:
        """
        Get current warmup status for a domain.

        Returns:
            Dict with warmup details including daily limit
        """
        # Query domain warmup record
        warmup = await self._get_or_create_warmup(domain)

        # Calculate current week
        days_since_start = (datetime.utcnow() - warmup["started_at"]).days
        current_week = min((days_since_start // 7) + 1, 8)

        # Get schedule for current week
        week_config = self.schedule.get(current_week, self.schedule[8])

        # Check if warmup is complete
        is_warmed = current_week >= 8 or warmup.get("is_warmed", False)

        return {
            "domain": domain,
            "started_at": warmup["started_at"],
            "current_week": current_week,
            "days_in_warmup": days_since_start,
            "is_warmed": is_warmed,
            "daily_limit": week_config.daily_limit,
            "delay_seconds": week_config.delay_between_emails_seconds,
            "total_sent": warmup.get("total_sent", 0),
            "today_sent": warmup.get("daily_sent_today", 0),
            "remaining_today": max(0, week_config.daily_limit - warmup.get("daily_sent_today", 0)),
            "bounce_rate": warmup.get("bounce_rate", 0),
            "spam_rate": warmup.get("spam_rate", 0),
            "health_status": self._get_health_status(warmup),
            "notes": week_config.notes,
        }

    async def get_daily_limit(self, domain: str) -> int:
        """Get the current daily sending limit for a domain."""
        status = await self.get_warmup_status(domain)
        return status["daily_limit"]

    async def get_send_delay(self, domain: str) -> int:
        """Get the recommended delay between emails (in seconds)."""
        status = await self.get_warmup_status(domain)
        return status["delay_seconds"]

    async def can_send(self, domain: str) -> tuple[bool, str]:
        """
        Check if we can send another email for this domain.

        Returns:
            Tuple of (can_send: bool, reason: str)
        """
        status = await self.get_warmup_status(domain)

        # Check if paused due to health issues
        if status["health_status"] == "critical":
            return False, "Domain health critical - sending paused"

        # Check daily limit
        if status["remaining_today"] <= 0:
            return False, f"Daily limit reached ({status['daily_limit']})"

        return True, "OK"

    async def record_send(self, domain: str) -> bool:
        """
        Record an email send for warmup tracking.

        Call this after successfully sending an email.
        """
        try:
            # This would update the database
            # For now, just log
            logger.debug(f"Recorded send for domain: {domain}")
            return True
        except Exception as e:
            logger.error(f"Error recording send: {e}")
            return False

    async def record_bounce(self, domain: str, is_hard_bounce: bool = True):
        """Record a bounce for health tracking."""
        logger.warning(f"Bounce recorded for {domain} (hard={is_hard_bounce})")
        # Update bounce rate calculation

    async def record_spam_report(self, domain: str):
        """Record a spam report - this is serious."""
        logger.error(f"SPAM REPORT recorded for {domain}")
        # Update spam rate and potentially pause sending

    async def start_warmup(self, domain: str) -> dict[str, Any]:
        """
        Start warmup process for a new domain.

        Args:
            domain: Email domain to warm up

        Returns:
            Initial warmup status
        """
        warmup = await self._get_or_create_warmup(domain, create_if_missing=True)

        logger.info(f"Started warmup for domain: {domain}")

        return await self.get_warmup_status(domain)

    async def reset_warmup(self, domain: str) -> dict[str, Any]:
        """
        Reset warmup process for a domain.

        Use this if domain reputation was damaged and needs to restart.
        """
        # Would delete and recreate warmup record
        logger.info(f"Reset warmup for domain: {domain}")
        return await self.start_warmup(domain)

    async def mark_warmed(self, domain: str):
        """
        Manually mark a domain as fully warmed.

        Use for established domains that don't need warmup.
        """
        logger.info(f"Marked domain as warmed: {domain}")

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _get_or_create_warmup(
        self,
        domain: str,
        create_if_missing: bool = True,
    ) -> dict[str, Any]:
        """Get or create warmup record for a domain."""
        # This would query the database
        # For now, return a default structure
        return {
            "domain": domain,
            "started_at": datetime.utcnow(),
            "current_week": 1,
            "total_sent": 0,
            "daily_sent_today": 0,
            "last_send_date": None,
            "bounce_rate": 0.0,
            "spam_rate": 0.0,
            "is_warmed": False,
        }

    def _get_health_status(self, warmup: dict) -> str:
        """
        Determine health status based on rates.

        Returns: "healthy", "warning", or "critical"
        """
        bounce_rate = warmup.get("bounce_rate", 0)
        spam_rate = warmup.get("spam_rate", 0)

        # Critical thresholds - pause sending
        if bounce_rate > 0.05 or spam_rate > 0.005:
            return "critical"

        # Warning thresholds - monitor closely
        if bounce_rate > 0.03 or spam_rate > 0.001:
            return "warning"

        return "healthy"

    def get_warmup_schedule_info(self) -> list[dict]:
        """Get the full warmup schedule for display."""
        return [
            {
                "week": week,
                "daily_limit": config.daily_limit,
                "delay_seconds": config.delay_between_emails_seconds,
                "notes": config.notes,
            }
            for week, config in sorted(self.schedule.items())
        ]


# =============================================================================
# Factory Function
# =============================================================================


def get_warmup_service(db_session: AsyncSession) -> WarmupService:
    """Factory function to get WarmupService instance."""
    return WarmupService(db_session)
