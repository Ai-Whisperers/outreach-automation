"""
Deliverability Routes.

API endpoints for monitoring email deliverability and domain warmup.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..dependencies import APIKeyDep
from ..logging_config import get_logger
from ..database.engine import get_db_session
from ..services.deliverability_service import (
    DeliverabilityService,
    DeliverabilityMetrics,
    HealthCheck,
)
from ..services.warmup_service import WarmupService
from ..services.email_validation_service import (
    EmailValidationService,
    ValidationResult,
)

router = APIRouter(prefix="/deliverability", tags=["deliverability"])
logger = get_logger("routes.deliverability")


# =============================================================================
# Health & Metrics Routes
# =============================================================================


@router.get("/health/{domain}")
async def check_domain_health(domain: str):
    """
    Check health status for a sending domain.

    Returns:
    - Health score (0-100)
    - Status (healthy, warning, critical)
    - Active alerts with recommended actions
    - Improvement recommendations
    """
    try:
        async with get_db_session() as db:
            service = DeliverabilityService(db)
            health = await service.check_health(domain)

            return {
                "domain": health.domain,
                "timestamp": health.timestamp,
                "health_score": health.health_score,
                "status": health.status,
                "alerts": [
                    {
                        "level": a.level,
                        "metric": a.metric,
                        "value": f"{a.current_value:.2%}",
                        "threshold": f"{a.threshold:.2%}",
                        "message": a.message,
                        "action": a.action,
                    }
                    for a in health.alerts
                ],
                "recommendations": health.recommendations,
            }

    except Exception as e:
        logger.error(f"Error checking domain health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{domain}")
async def get_deliverability_metrics(
    domain: str,
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
):
    """
    Get deliverability metrics for a domain.

    Periods:
    - daily: Last 24 hours
    - weekly: Last 7 days
    - monthly: Last 30 days
    """
    try:
        async with get_db_session() as db:
            service = DeliverabilityService(db)
            metrics = await service.get_metrics(domain, period=period)

            return {
                "domain": metrics.domain,
                "period": metrics.period,
                "date_range": {
                    "start": metrics.start_date,
                    "end": metrics.end_date,
                },
                "volume": {
                    "sent": metrics.total_sent,
                    "delivered": metrics.delivered,
                    "bounced": metrics.bounced,
                    "soft_bounced": metrics.soft_bounced,
                    "hard_bounced": metrics.hard_bounced,
                },
                "engagement": {
                    "opens": metrics.opens,
                    "unique_opens": metrics.unique_opens,
                    "clicks": metrics.clicks,
                    "unique_clicks": metrics.unique_clicks,
                    "replies": metrics.replies,
                },
                "negative_signals": {
                    "spam_reports": metrics.spam_reports,
                    "unsubscribes": metrics.unsubscribes,
                },
                "rates": {
                    "delivery_rate": f"{metrics.delivery_rate:.1%}",
                    "bounce_rate": f"{metrics.bounce_rate:.1%}",
                    "spam_rate": f"{metrics.spam_rate:.2%}",
                    "open_rate": f"{metrics.open_rate:.1%}",
                    "click_rate": f"{metrics.click_rate:.1%}",
                    "reply_rate": f"{metrics.reply_rate:.1%}",
                },
                "health_score": metrics.health_score,
            }

    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend/{domain}")
async def get_deliverability_trend(
    domain: str,
    days: int = Query(14, ge=1, le=30),
):
    """
    Get daily deliverability trend for a domain.

    Returns day-by-day metrics for trend analysis.
    """
    try:
        async with get_db_session() as db:
            service = DeliverabilityService(db)
            trend = await service.get_daily_trend(domain, days=days)

            return {
                "domain": domain,
                "days": days,
                "trend": trend,
            }

    except Exception as e:
        logger.error(f"Error getting trend: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Warmup Routes
# =============================================================================


@router.get("/warmup/{domain}")
async def get_warmup_status(domain: str):
    """
    Get warmup status for a domain.

    Returns:
    - Current week in warmup process
    - Daily sending limit
    - Recommended delay between emails
    - Health metrics
    """
    try:
        async with get_db_session() as db:
            service = WarmupService(db)
            status = await service.get_warmup_status(domain)

            return status

    except Exception as e:
        logger.error(f"Error getting warmup status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/warmup/{domain}/start")
async def start_domain_warmup(
    domain: str,
    api_key: APIKeyDep,
):
    """
    Start warmup process for a new domain.

    Initializes tracking and returns the warmup schedule.
    """
    try:
        async with get_db_session() as db:
            service = WarmupService(db)
            status = await service.start_warmup(domain)

            return {
                "status": "started",
                "domain": domain,
                **status,
            }

    except Exception as e:
        logger.error(f"Error starting warmup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/warmup/{domain}/reset")
async def reset_domain_warmup(
    domain: str,
    api_key: APIKeyDep,
):
    """
    Reset warmup process for a domain.

    Use if domain reputation was damaged and needs to restart.
    """
    try:
        async with get_db_session() as db:
            service = WarmupService(db)
            status = await service.reset_warmup(domain)

            return {
                "status": "reset",
                "domain": domain,
                **status,
            }

    except Exception as e:
        logger.error(f"Error resetting warmup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/warmup/schedule")
async def get_warmup_schedule():
    """
    Get the warmup schedule configuration.

    Shows daily limits and delays for each week.
    """
    try:
        async with get_db_session() as db:
            service = WarmupService(db)
            schedule = service.get_warmup_schedule_info()

            return {
                "schedule": schedule,
                "notes": [
                    "Week 1-4: Conservative ramp-up period",
                    "Week 5-7: Gradual increase to full capacity",
                    "Week 8+: Full sending capacity achieved",
                ],
            }

    except Exception as e:
        logger.error(f"Error getting schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/warmup/{domain}/can-send")
async def check_can_send(domain: str):
    """
    Check if we can send another email for this domain.

    Returns whether daily limit allows more sending.
    """
    try:
        async with get_db_session() as db:
            service = WarmupService(db)
            can_send, reason = await service.can_send(domain)

            return {
                "can_send": can_send,
                "reason": reason,
            }

    except Exception as e:
        logger.error(f"Error checking can_send: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Email Validation Routes
# =============================================================================


class EmailValidationRequest(BaseModel):
    """Request to validate emails."""

    emails: list[str]
    check_mx: bool = True


class SingleEmailValidation(BaseModel):
    """Request to validate a single email."""

    email: str
    check_mx: bool = True


@router.post("/validate")
async def validate_email(request: SingleEmailValidation):
    """
    Validate a single email address.

    Checks:
    - Format validation
    - Domain typo detection
    - Disposable email detection
    - Role-based email detection
    - MX record verification
    """
    try:
        service = EmailValidationService()
        result = await service.validate(
            email=request.email,
            check_mx=request.check_mx,
        )

        return {
            "email": result.email,
            "is_valid": result.is_valid,
            "risk_score": result.risk_score,
            "risk_reasons": result.risk_reasons,
            "domain": result.domain,
            "provider": result.provider,
            "suggestion": result.suggestion,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "reason": c.reason,
                }
                for c in result.checks
            ],
        }

    except Exception as e:
        logger.error(f"Error validating email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate/batch")
async def validate_emails_batch(request: EmailValidationRequest):
    """
    Validate multiple email addresses.

    Returns validation results for each email.
    """
    try:
        service = EmailValidationService()
        results = await service.validate_batch(
            emails=request.emails,
            check_mx=request.check_mx,
        )

        valid_count = sum(1 for r in results if r.is_valid)
        invalid_count = len(results) - valid_count

        return {
            "total": len(results),
            "valid": valid_count,
            "invalid": invalid_count,
            "results": [
                {
                    "email": r.email,
                    "is_valid": r.is_valid,
                    "risk_score": r.risk_score,
                    "risk_reasons": r.risk_reasons,
                    "suggestion": r.suggestion,
                }
                for r in results
            ],
        }

    except Exception as e:
        logger.error(f"Error validating emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validate/quick")
async def quick_validate_email(email: str):
    """
    Quick email validation (format + typo only).

    Faster than full validation, no DNS lookups.
    """
    try:
        service = EmailValidationService()
        is_valid, message = service.quick_validate(email)

        return {
            "email": email,
            "is_valid": is_valid,
            "message": message,
        }

    except Exception as e:
        logger.error(f"Error quick validating: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Dashboard Route
# =============================================================================


@router.get("/dashboard")
async def get_deliverability_dashboard(
    domain: str | None = Query(None),
):
    """
    Get comprehensive deliverability dashboard.

    Combines health, metrics, warmup status, and recommendations.
    """
    try:
        # Use default domain if not specified
        domain = domain or "ai-whisperers.com"

        async with get_db_session() as db:
            deliverability = DeliverabilityService(db)
            warmup = WarmupService(db)

            health = await deliverability.check_health(domain)
            metrics = await deliverability.get_metrics(domain, period="weekly")
            warmup_status = await warmup.get_warmup_status(domain)

            return {
                "domain": domain,
                "health": {
                    "score": health.health_score,
                    "status": health.status,
                    "alert_count": len(health.alerts),
                },
                "metrics": {
                    "sent_7d": metrics.total_sent,
                    "delivery_rate": f"{metrics.delivery_rate:.1%}",
                    "open_rate": f"{metrics.open_rate:.1%}",
                    "reply_rate": f"{metrics.reply_rate:.1%}",
                    "bounce_rate": f"{metrics.bounce_rate:.1%}",
                },
                "warmup": {
                    "week": warmup_status["current_week"],
                    "is_warmed": warmup_status["is_warmed"],
                    "daily_limit": warmup_status["daily_limit"],
                    "remaining_today": warmup_status["remaining_today"],
                },
                "alerts": [
                    {"level": a.level, "message": a.message}
                    for a in health.alerts
                ],
                "recommendations": health.recommendations[:3],
            }

    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))
