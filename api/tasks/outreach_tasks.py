"""
Celery tasks for outreach automation.

Task Types:
1. Scheduling Tasks - Schedule messages for sending
2. Sending Tasks - Actually send messages via channels
3. Engagement Tasks - Process webhooks and tracking
4. Polling Tasks - Check for LinkedIn connection acceptance
5. Analytics Tasks - Aggregate daily stats
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from celery import Task

from ..database.outreach_models import (
    MessageStatus,
    MessageType,
    OutreachChannel,
    ProspectStatus,
)
from ..logging_config import get_logger
from .celery_app import celery_app

logger = get_logger("tasks.outreach")


# =============================================================================
# Async Task Base
# =============================================================================


class AsyncTask(Task):
    """Base task that supports async functions."""

    def __call__(self, *args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.run(*args, **kwargs))
        finally:
            loop.close()


# =============================================================================
# Scheduling Tasks
# =============================================================================


@celery_app.task(
    base=AsyncTask,
    bind=True,
    name="outreach.schedule_daily_batch",
    max_retries=3,
)
async def schedule_daily_batch_task(self, campaign_id: int) -> dict[str, Any]:
    """
    Schedule daily batch of outreach messages.

    Runs via Celery Beat at start of business day (9 AM).

    Steps:
    1. Check daily quotas (LinkedIn 20/day, Email 50/day)
    2. Get prospects ready for outreach
    3. Generate personalized messages
    4. Schedule messages with staggered timing
    """
    from ..services.outreach_rate_limiter import get_outreach_rate_limiter

    logger.info(f"Scheduling daily batch for campaign {campaign_id}")

    rate_limiter = get_outreach_rate_limiter()

    result = {
        "campaign_id": campaign_id,
        "linkedin_scheduled": 0,
        "email_scheduled": 0,
        "errors": [],
    }

    try:
        # Check LinkedIn quota
        li_allowed, li_remaining = await rate_limiter.check_quota(
            "linkedin_connection", campaign_id
        )

        if li_allowed and li_remaining > 0:
            # Schedule LinkedIn connection requests
            linkedin_count = await _schedule_linkedin_batch(
                campaign_id, li_remaining
            )
            result["linkedin_scheduled"] = linkedin_count

        # Check email quota
        email_allowed, email_remaining = await rate_limiter.check_quota(
            "email", campaign_id
        )

        if email_allowed and email_remaining > 0:
            # Schedule emails
            email_count = await _schedule_email_batch(
                campaign_id, email_remaining
            )
            result["email_scheduled"] = email_count

        logger.info(
            f"Daily batch scheduled: {result['linkedin_scheduled']} LinkedIn, "
            f"{result['email_scheduled']} emails"
        )

        return result

    except Exception as e:
        logger.error(f"Error scheduling daily batch: {e}")
        result["errors"].append(str(e))
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes


async def _schedule_linkedin_batch(campaign_id: int, limit: int) -> int:
    """Schedule LinkedIn connection requests batch."""
    # This would use the prospect service and outreach service
    # Implementation depends on database session management
    logger.info(f"Scheduling up to {limit} LinkedIn connections for campaign {campaign_id}")
    return 0  # Placeholder - implement with actual DB operations


async def _schedule_email_batch(campaign_id: int, limit: int) -> int:
    """Schedule email batch."""
    logger.info(f"Scheduling up to {limit} emails for campaign {campaign_id}")
    return 0  # Placeholder - implement with actual DB operations


@celery_app.task(
    base=AsyncTask,
    name="outreach.schedule_followups",
)
async def schedule_followups_task(campaign_id: int) -> dict[str, Any]:
    """
    Schedule follow-up messages based on sequence timing.

    Email Sequence:
    - Day 0: Initial email
    - Day 1: Follow-up 1 (if no reply)
    - Day 4: Follow-up 2 (if no reply)
    - Day 8: Follow-up 3 (if no reply)
    - Day 14: Follow-up 4 / Break-up email

    Only schedules if:
    - Previous message was sent
    - No reply received
    - Time threshold passed
    """
    logger.info(f"Checking follow-ups for campaign {campaign_id}")

    # Follow-up schedule: (previous_type, next_type, days_after_previous)
    FOLLOWUP_SCHEDULE = [
        (MessageType.EMAIL_INITIAL, MessageType.EMAIL_FOLLOWUP_1, 1),
        (MessageType.EMAIL_FOLLOWUP_1, MessageType.EMAIL_FOLLOWUP_2, 3),
        (MessageType.EMAIL_FOLLOWUP_2, MessageType.EMAIL_FOLLOWUP_3, 4),
        (MessageType.EMAIL_FOLLOWUP_3, MessageType.EMAIL_FOLLOWUP_4, 6),
    ]

    result = {
        "campaign_id": campaign_id,
        "followups_scheduled": 0,
        "errors": [],
    }

    # Implementation would query DB for prospects needing follow-ups
    # and schedule the appropriate next message

    return result


# =============================================================================
# Sending Tasks
# =============================================================================


@celery_app.task(
    base=AsyncTask,
    bind=True,
    name="outreach.send_linkedin_connection",
    max_retries=3,
    default_retry_delay=300,
)
async def send_linkedin_connection_task(
    self,
    message_id: int,
    prospect_id: int,
) -> dict[str, Any]:
    """
    Send LinkedIn connection request.

    Rate Limit: Max 20 connection requests per day
    Retry: 3 times with 5-minute delay
    """
    from ..services.linkedin_service import get_linkedin_service
    from ..services.outreach_rate_limiter import get_outreach_rate_limiter

    logger.info(f"Sending LinkedIn connection for message {message_id}")

    result = {
        "message_id": message_id,
        "prospect_id": prospect_id,
        "success": False,
    }

    try:
        # Get services
        linkedin_service = get_linkedin_service()
        rate_limiter = get_outreach_rate_limiter()

        # Check quota before sending
        # Note: campaign_id would need to be passed or fetched from message
        campaign_id = 1  # Placeholder - should be fetched from message

        allowed, remaining = await rate_limiter.check_quota(
            "linkedin_connection", campaign_id
        )

        if not allowed:
            logger.warning(f"LinkedIn quota exceeded for campaign {campaign_id}")
            raise self.retry(
                countdown=3600,  # Retry in 1 hour
                max_retries=24,
                exc=Exception("LinkedIn daily quota exceeded")
            )

        # Get message and prospect details from DB
        # This is a placeholder - actual implementation needs DB session
        profile_url = "https://linkedin.com/in/example"  # From prospect
        message_content = "Connection message"  # From message

        # Initialize LinkedIn service and send
        if not await linkedin_service.initialize():
            raise Exception("Failed to initialize LinkedIn service")

        connection_result = await linkedin_service.send_connection_request(
            profile_url=profile_url,
            message=message_content
        )

        await linkedin_service.close()

        if connection_result.success:
            # Increment usage
            await rate_limiter.increment_usage("linkedin_connection", campaign_id)

            # Update message status in DB (placeholder)
            result["success"] = True
            result["request_id"] = connection_result.request_id

            logger.info(f"LinkedIn connection sent: {message_id}")
        else:
            result["error"] = connection_result.error
            logger.error(f"LinkedIn connection failed: {connection_result.error}")

        return result

    except Exception as e:
        logger.error(f"Error sending LinkedIn connection: {e}")
        result["error"] = str(e)
        raise


@celery_app.task(
    base=AsyncTask,
    bind=True,
    name="outreach.send_email",
    max_retries=5,
    default_retry_delay=60,
)
async def send_email_task(
    self,
    message_id: int,
    prospect_id: int,
) -> dict[str, Any]:
    """
    Send email via SendGrid.

    Includes:
    - Open tracking pixel
    - Click tracking
    - Unsubscribe link
    """
    from ..services.email_service import get_email_service
    from ..services.outreach_rate_limiter import get_outreach_rate_limiter

    logger.info(f"Sending email for message {message_id}")

    result = {
        "message_id": message_id,
        "prospect_id": prospect_id,
        "success": False,
    }

    try:
        email_service = get_email_service()
        rate_limiter = get_outreach_rate_limiter()

        # Placeholder - should be fetched from DB
        campaign_id = 1
        to_email = "recipient@example.com"
        subject = "Email subject"
        html_content = "<p>Email body</p>"

        # Check quota
        allowed, remaining = await rate_limiter.check_quota("email", campaign_id)

        if not allowed:
            logger.warning(f"Email quota exceeded for campaign {campaign_id}")
            raise self.retry(
                countdown=3600,
                max_retries=24,
                exc=Exception("Email daily quota exceeded")
            )

        # Send email
        email_result = await email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            tracking_id=str(message_id),
        )

        if email_result.success:
            await rate_limiter.increment_usage("email", campaign_id)

            result["success"] = True
            result["sendgrid_id"] = email_result.message_id

            logger.info(f"Email sent: {message_id}")
        else:
            result["error"] = email_result.error

            # Check for bounce
            if email_result.error and "bounce" in email_result.error.lower():
                logger.warning(f"Email bounced: {message_id}")
                # Mark prospect as bounced in DB

        return result

    except Exception as e:
        logger.error(f"Error sending email: {e}")
        result["error"] = str(e)
        raise


# =============================================================================
# Engagement Processing Tasks
# =============================================================================


@celery_app.task(
    base=AsyncTask,
    name="outreach.process_engagement_webhook",
)
async def process_engagement_webhook_task(
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Process engagement webhooks from email/LinkedIn.

    Event Types:
    - email_open
    - email_click
    - email_reply
    - email_bounce
    - email_unsubscribe
    - linkedin_connection_accepted
    - linkedin_message_reply
    """
    logger.info(f"Processing engagement event: {event_type}")

    result = {
        "event_type": event_type,
        "processed": False,
    }

    try:
        tracking_id = payload.get("tracking_id") or payload.get("message_id")

        if not tracking_id:
            logger.warning(f"No tracking_id in payload: {payload}")
            return result

        # Handle specific events
        if event_type == "email_open":
            # Update prospect status to "engaged"
            logger.info(f"Email opened: {tracking_id}")

        elif event_type == "email_click":
            # Track click, update engagement score
            logger.info(f"Email clicked: {tracking_id}")

        elif event_type == "email_reply":
            # Update prospect to "replied", cancel follow-ups
            logger.info(f"Email reply: {tracking_id}")
            await _cancel_pending_followups(tracking_id)

        elif event_type == "email_bounce":
            # Mark prospect as bounced
            logger.info(f"Email bounced: {tracking_id}")

        elif event_type == "email_unsubscribe":
            # Mark prospect as opted_out
            logger.info(f"Email unsubscribe: {tracking_id}")

        elif event_type == "linkedin_connection_accepted":
            # Update prospect to "connected"
            logger.info(f"LinkedIn connection accepted: {tracking_id}")

        elif event_type == "linkedin_message_reply":
            # Update prospect to "replied"
            logger.info(f"LinkedIn reply: {tracking_id}")
            await _cancel_pending_followups(tracking_id)

        result["processed"] = True
        return result

    except Exception as e:
        logger.error(f"Error processing engagement: {e}")
        result["error"] = str(e)
        return result


async def _cancel_pending_followups(tracking_id: str):
    """Cancel pending follow-up messages for a prospect."""
    # Implementation would update DB to cancel scheduled follow-ups
    logger.info(f"Cancelling follow-ups for: {tracking_id}")


# =============================================================================
# Polling Tasks
# =============================================================================


@celery_app.task(
    base=AsyncTask,
    name="outreach.check_linkedin_connections",
)
async def check_linkedin_connections_task(campaign_id: int) -> dict[str, Any]:
    """
    Periodic task to check for accepted LinkedIn connections.

    LinkedIn doesn't provide webhooks, so we poll.
    Runs every 4 hours.
    """
    from ..services.linkedin_service import get_linkedin_service

    logger.info(f"Checking LinkedIn connections for campaign {campaign_id}")

    result = {
        "campaign_id": campaign_id,
        "checked": 0,
        "newly_connected": 0,
    }

    try:
        linkedin_service = get_linkedin_service()

        if not await linkedin_service.initialize():
            logger.error("Failed to initialize LinkedIn service")
            return result

        # Get pending invitations
        pending = await linkedin_service.get_pending_invitations()
        result["checked"] = len(pending)

        # For each pending, check if now connected
        # This would need to be matched against our database

        await linkedin_service.close()

        logger.info(
            f"LinkedIn check complete: {result['checked']} checked, "
            f"{result['newly_connected']} newly connected"
        )

        return result

    except Exception as e:
        logger.error(f"Error checking LinkedIn connections: {e}")
        result["error"] = str(e)
        return result


# =============================================================================
# Analytics Tasks
# =============================================================================


@celery_app.task(
    base=AsyncTask,
    name="outreach.aggregate_daily_analytics",
)
async def aggregate_daily_analytics_task() -> dict[str, Any]:
    """
    Aggregate daily analytics for all campaigns.

    Runs at end of day via Celery Beat.
    """
    logger.info("Aggregating daily analytics")

    result = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "campaigns_processed": 0,
    }

    # Implementation would query engagement events and aggregate stats

    return result


# =============================================================================
# Batch Orchestration Tasks
# =============================================================================


@celery_app.task(name="outreach.dispatch_linkedin_batch")
def dispatch_linkedin_batch_task(
    message_ids: list[int],
    prospect_ids: list[int],
    campaign_id: int,
):
    """
    Dispatch LinkedIn sends with human-like delays.

    Spreads sends across the day with random intervals.
    """
    import random

    logger.info(f"Dispatching {len(message_ids)} LinkedIn connections")

    # Spread across 8 hours (9 AM - 5 PM equivalent)
    total_minutes = 8 * 60
    interval = total_minutes // len(message_ids) if message_ids else 0

    for i, (message_id, prospect_id) in enumerate(zip(message_ids, prospect_ids)):
        # Add randomness (+/- 5 minutes)
        delay = (i * interval * 60) + random.randint(-300, 300)
        delay = max(0, delay)  # Ensure non-negative

        send_linkedin_connection_task.apply_async(
            kwargs={"message_id": message_id, "prospect_id": prospect_id},
            countdown=delay
        )


@celery_app.task(name="outreach.dispatch_email_batch")
def dispatch_email_batch_task(
    message_ids: list[int],
    prospect_ids: list[int],
    campaign_id: int,
):
    """
    Dispatch email sends with professional timing.

    Stagger emails to avoid spam detection.
    """
    import random

    logger.info(f"Dispatching {len(message_ids)} emails")

    for i, (message_id, prospect_id) in enumerate(zip(message_ids, prospect_ids)):
        # Stagger by 30-60 seconds each
        delay = i * random.randint(30, 60)

        send_email_task.apply_async(
            kwargs={"message_id": message_id, "prospect_id": prospect_id},
            countdown=delay
        )


# =============================================================================
# Celery Beat Schedule
# =============================================================================

# Note: This should be added to celery_app.py
OUTREACH_BEAT_SCHEDULE = {
    # Schedule daily outreach at 9 AM UTC
    "schedule-daily-outreach": {
        "task": "outreach.schedule_daily_batch",
        "schedule": 86400,  # Daily (use crontab in production)
        "args": (1,),  # Campaign ID - would be dynamic in production
    },
    # Check for needed follow-ups every 2 hours
    "check-followups": {
        "task": "outreach.schedule_followups",
        "schedule": 7200,  # Every 2 hours
        "args": (1,),
    },
    # Check LinkedIn connections every 4 hours
    "check-linkedin-connections": {
        "task": "outreach.check_linkedin_connections",
        "schedule": 14400,  # Every 4 hours
        "args": (1,),
    },
    # Aggregate analytics at midnight
    "aggregate-daily-analytics": {
        "task": "outreach.aggregate_daily_analytics",
        "schedule": 86400,  # Daily
    },
}
