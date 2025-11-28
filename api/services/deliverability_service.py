"""
Deliverability Monitoring Service.

Tracks email deliverability metrics and health scores.
Provides alerts when metrics exceed thresholds.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.outreach_models import (
    EngagementEvent,
    MessageStatus,
    OutreachChannel,
    OutreachMessage,
)
from ..logging_config import get_logger

logger = get_logger("services.deliverability")


# =============================================================================
# Models
# =============================================================================


class DeliverabilityMetrics(BaseModel):
    """Deliverability metrics for a domain/period."""

    domain: str
    period: str  # daily, weekly, monthly
    start_date: datetime
    end_date: datetime

    # Volume
    total_sent: int
    delivered: int
    bounced: int
    soft_bounced: int
    hard_bounced: int

    # Engagement
    opens: int
    unique_opens: int
    clicks: int
    unique_clicks: int
    replies: int

    # Negative signals
    spam_reports: int
    unsubscribes: int

    # Calculated rates
    delivery_rate: float  # Target: > 95%
    bounce_rate: float  # Target: < 3%
    spam_rate: float  # Target: < 0.1%
    open_rate: float  # Benchmark: 15-25%
    click_rate: float  # Benchmark: 2-5%
    reply_rate: float  # Benchmark: 1-5%

    # Health
    health_score: int  # 0-100


class HealthAlert(BaseModel):
    """Alert for deliverability issues."""

    level: str  # info, warning, critical
    metric: str
    current_value: float
    threshold: float
    message: str
    action: str


class HealthCheck(BaseModel):
    """Overall health check result."""

    domain: str
    timestamp: datetime
    health_score: int
    status: str  # healthy, warning, critical
    alerts: list[HealthAlert]
    recommendations: list[str]


# =============================================================================
# Alert Thresholds
# =============================================================================


ALERT_THRESHOLDS = {
    "bounce_rate": {
        "warning": 0.03,  # 3%
        "critical": 0.05,  # 5%
    },
    "spam_rate": {
        "warning": 0.001,  # 0.1%
        "critical": 0.005,  # 0.5%
    },
    "delivery_rate": {
        "warning": 0.95,  # Below 95%
        "critical": 0.90,  # Below 90%
    },
    "open_rate": {
        "warning": 0.10,  # Below 10%
        "critical": 0.05,  # Below 5%
    },
}


# =============================================================================
# Deliverability Service
# =============================================================================


class DeliverabilityService:
    """
    Monitor and report on email deliverability.

    Features:
    - Track delivery, engagement, and negative signal rates
    - Calculate health scores
    - Generate alerts when thresholds are exceeded
    - Provide actionable recommendations
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def get_metrics(
        self,
        domain: str,
        period: str = "daily",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> DeliverabilityMetrics:
        """
        Get deliverability metrics for a domain.

        Args:
            domain: Email sending domain
            period: "daily", "weekly", or "monthly"
            start_date: Start of period (defaults based on period)
            end_date: End of period (defaults to now)

        Returns:
            DeliverabilityMetrics with all calculated rates
        """
        # Calculate date range
        now = datetime.utcnow()
        end_date = end_date or now

        if not start_date:
            if period == "daily":
                start_date = end_date - timedelta(days=1)
            elif period == "weekly":
                start_date = end_date - timedelta(days=7)
            else:  # monthly
                start_date = end_date - timedelta(days=30)

        # Query metrics from database
        metrics_data = await self._query_metrics(domain, start_date, end_date)

        # Calculate rates
        total = metrics_data["total_sent"] or 1  # Avoid division by zero

        delivery_rate = metrics_data["delivered"] / total if total > 0 else 0
        bounce_rate = metrics_data["bounced"] / total if total > 0 else 0
        spam_rate = metrics_data["spam_reports"] / total if total > 0 else 0
        open_rate = metrics_data["unique_opens"] / total if total > 0 else 0
        click_rate = metrics_data["unique_clicks"] / total if total > 0 else 0
        reply_rate = metrics_data["replies"] / total if total > 0 else 0

        # Calculate health score
        health_score = self._calculate_health_score(
            delivery_rate=delivery_rate,
            bounce_rate=bounce_rate,
            spam_rate=spam_rate,
            open_rate=open_rate,
        )

        return DeliverabilityMetrics(
            domain=domain,
            period=period,
            start_date=start_date,
            end_date=end_date,
            total_sent=metrics_data["total_sent"],
            delivered=metrics_data["delivered"],
            bounced=metrics_data["bounced"],
            soft_bounced=metrics_data["soft_bounced"],
            hard_bounced=metrics_data["hard_bounced"],
            opens=metrics_data["opens"],
            unique_opens=metrics_data["unique_opens"],
            clicks=metrics_data["clicks"],
            unique_clicks=metrics_data["unique_clicks"],
            replies=metrics_data["replies"],
            spam_reports=metrics_data["spam_reports"],
            unsubscribes=metrics_data["unsubscribes"],
            delivery_rate=round(delivery_rate, 4),
            bounce_rate=round(bounce_rate, 4),
            spam_rate=round(spam_rate, 4),
            open_rate=round(open_rate, 4),
            click_rate=round(click_rate, 4),
            reply_rate=round(reply_rate, 4),
            health_score=health_score,
        )

    async def check_health(self, domain: str) -> HealthCheck:
        """
        Perform health check for a domain.

        Returns:
            HealthCheck with score, status, and any alerts
        """
        metrics = await self.get_metrics(domain, period="daily")

        alerts = []

        # Check bounce rate
        if metrics.bounce_rate > ALERT_THRESHOLDS["bounce_rate"]["critical"]:
            alerts.append(HealthAlert(
                level="critical",
                metric="bounce_rate",
                current_value=metrics.bounce_rate,
                threshold=ALERT_THRESHOLDS["bounce_rate"]["critical"],
                message=f"Bounce rate {metrics.bounce_rate:.1%} exceeds critical threshold",
                action="Pause sending immediately. Clean email list and verify addresses.",
            ))
        elif metrics.bounce_rate > ALERT_THRESHOLDS["bounce_rate"]["warning"]:
            alerts.append(HealthAlert(
                level="warning",
                metric="bounce_rate",
                current_value=metrics.bounce_rate,
                threshold=ALERT_THRESHOLDS["bounce_rate"]["warning"],
                message=f"Bounce rate {metrics.bounce_rate:.1%} is elevated",
                action="Review recent imports. Enable email validation before sending.",
            ))

        # Check spam rate
        if metrics.spam_rate > ALERT_THRESHOLDS["spam_rate"]["critical"]:
            alerts.append(HealthAlert(
                level="critical",
                metric="spam_rate",
                current_value=metrics.spam_rate,
                threshold=ALERT_THRESHOLDS["spam_rate"]["critical"],
                message=f"Spam rate {metrics.spam_rate:.2%} is dangerously high",
                action="STOP ALL SENDING. Review email content and targeting.",
            ))
        elif metrics.spam_rate > ALERT_THRESHOLDS["spam_rate"]["warning"]:
            alerts.append(HealthAlert(
                level="warning",
                metric="spam_rate",
                current_value=metrics.spam_rate,
                threshold=ALERT_THRESHOLDS["spam_rate"]["warning"],
                message=f"Spam rate {metrics.spam_rate:.2%} is elevated",
                action="Review email content. Ensure clear unsubscribe link.",
            ))

        # Check delivery rate
        if metrics.delivery_rate < ALERT_THRESHOLDS["delivery_rate"]["critical"]:
            alerts.append(HealthAlert(
                level="critical",
                metric="delivery_rate",
                current_value=metrics.delivery_rate,
                threshold=ALERT_THRESHOLDS["delivery_rate"]["critical"],
                message=f"Delivery rate {metrics.delivery_rate:.1%} is critically low",
                action="Check DNS settings (SPF, DKIM, DMARC). Contact SendGrid support.",
            ))
        elif metrics.delivery_rate < ALERT_THRESHOLDS["delivery_rate"]["warning"]:
            alerts.append(HealthAlert(
                level="warning",
                metric="delivery_rate",
                current_value=metrics.delivery_rate,
                threshold=ALERT_THRESHOLDS["delivery_rate"]["warning"],
                message=f"Delivery rate {metrics.delivery_rate:.1%} is below target",
                action="Review bounce reasons. Verify sending domain configuration.",
            ))

        # Check open rate (informational)
        if metrics.open_rate < ALERT_THRESHOLDS["open_rate"]["warning"]:
            alerts.append(HealthAlert(
                level="warning",
                metric="open_rate",
                current_value=metrics.open_rate,
                threshold=ALERT_THRESHOLDS["open_rate"]["warning"],
                message=f"Open rate {metrics.open_rate:.1%} is below benchmark",
                action="Test subject lines. Verify emails aren't landing in spam.",
            ))

        # Determine overall status
        has_critical = any(a.level == "critical" for a in alerts)
        has_warning = any(a.level == "warning" for a in alerts)

        if has_critical:
            status = "critical"
        elif has_warning:
            status = "warning"
        else:
            status = "healthy"

        # Generate recommendations
        recommendations = self._generate_recommendations(metrics, alerts)

        return HealthCheck(
            domain=domain,
            timestamp=datetime.utcnow(),
            health_score=metrics.health_score,
            status=status,
            alerts=alerts,
            recommendations=recommendations,
        )

    async def get_daily_trend(
        self,
        domain: str,
        days: int = 14,
    ) -> list[dict[str, Any]]:
        """
        Get daily metrics trend for a domain.

        Returns list of daily metric snapshots.
        """
        trend = []
        end_date = datetime.utcnow()

        for i in range(days):
            day_end = end_date - timedelta(days=i)
            day_start = day_end - timedelta(days=1)

            metrics = await self.get_metrics(
                domain=domain,
                period="daily",
                start_date=day_start,
                end_date=day_end,
            )

            trend.append({
                "date": day_start.date().isoformat(),
                "sent": metrics.total_sent,
                "delivered": metrics.delivered,
                "bounced": metrics.bounced,
                "opens": metrics.unique_opens,
                "clicks": metrics.unique_clicks,
                "replies": metrics.replies,
                "delivery_rate": metrics.delivery_rate,
                "open_rate": metrics.open_rate,
                "health_score": metrics.health_score,
            })

        return list(reversed(trend))  # Oldest first

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _query_metrics(
        self,
        domain: str,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, int]:
        """Query raw metrics from database."""
        # This would query OutreachMessage and EngagementEvent tables
        # For now, return placeholder structure
        return {
            "total_sent": 0,
            "delivered": 0,
            "bounced": 0,
            "soft_bounced": 0,
            "hard_bounced": 0,
            "opens": 0,
            "unique_opens": 0,
            "clicks": 0,
            "unique_clicks": 0,
            "replies": 0,
            "spam_reports": 0,
            "unsubscribes": 0,
        }

    def _calculate_health_score(
        self,
        delivery_rate: float,
        bounce_rate: float,
        spam_rate: float,
        open_rate: float,
    ) -> int:
        """
        Calculate overall health score (0-100).

        Weighted factors:
        - Delivery rate: 40%
        - Bounce rate: 25%
        - Spam rate: 25%
        - Open rate: 10%
        """
        score = 0

        # Delivery rate (40 points max)
        if delivery_rate >= 0.98:
            score += 40
        elif delivery_rate >= 0.95:
            score += 35
        elif delivery_rate >= 0.90:
            score += 25
        elif delivery_rate >= 0.80:
            score += 15
        else:
            score += 0

        # Bounce rate (25 points max, lower is better)
        if bounce_rate <= 0.01:
            score += 25
        elif bounce_rate <= 0.02:
            score += 20
        elif bounce_rate <= 0.03:
            score += 15
        elif bounce_rate <= 0.05:
            score += 10
        else:
            score += 0

        # Spam rate (25 points max, lower is better)
        if spam_rate == 0:
            score += 25
        elif spam_rate <= 0.001:
            score += 20
        elif spam_rate <= 0.003:
            score += 10
        else:
            score += 0

        # Open rate (10 points max)
        if open_rate >= 0.25:
            score += 10
        elif open_rate >= 0.20:
            score += 8
        elif open_rate >= 0.15:
            score += 6
        elif open_rate >= 0.10:
            score += 4
        else:
            score += 2

        return min(100, max(0, score))

    def _generate_recommendations(
        self,
        metrics: DeliverabilityMetrics,
        alerts: list[HealthAlert],
    ) -> list[str]:
        """Generate actionable recommendations based on metrics."""
        recommendations = []

        if not alerts:
            recommendations.append("Metrics look healthy. Continue monitoring.")
            return recommendations

        # Bounce-related recommendations
        if metrics.bounce_rate > 0.02:
            recommendations.append("Enable email validation before importing prospects")
            recommendations.append("Review recent prospect sources for data quality")

        # Spam-related recommendations
        if metrics.spam_rate > 0:
            recommendations.append("Review email content for spam triggers")
            recommendations.append("Ensure unsubscribe link is visible and working")
            recommendations.append("Consider reducing sending frequency")

        # Delivery-related recommendations
        if metrics.delivery_rate < 0.95:
            recommendations.append("Verify SPF, DKIM, and DMARC DNS records")
            recommendations.append("Check if sending IP is on any blacklists")
            recommendations.append("Contact SendGrid support for reputation review")

        # Open rate recommendations
        if metrics.open_rate < 0.15:
            recommendations.append("A/B test subject lines for better open rates")
            recommendations.append("Check if emails are landing in spam folders")
            recommendations.append("Review send timing for optimal engagement")

        return recommendations


# =============================================================================
# Factory Function
# =============================================================================


def get_deliverability_service(db_session: AsyncSession) -> DeliverabilityService:
    """Factory function to get DeliverabilityService instance."""
    return DeliverabilityService(db_session)
