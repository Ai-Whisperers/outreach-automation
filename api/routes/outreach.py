"""
Outreach execution and webhook routes.

Handles message sending, scheduling, and engagement tracking.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks

from ..dependencies import APIKeyDep
from ..logging_config import get_logger
from ..models.outreach_models import (
    ScheduleRequest,
    ScheduleResponse,
    SendRequest,
    SendResponse,
    QuotaStatus,
    AnalyticsDashboard,
    ChannelType,
)
from ..services.prospect_service import get_prospect_service
from ..services.outreach_rate_limiter import get_outreach_rate_limiter

router = APIRouter(prefix="/outreach", tags=["outreach-execution"])
logger = get_logger("routes.outreach")


# =============================================================================
# Scheduling Endpoints
# =============================================================================


@router.post("/schedule", response_model=ScheduleResponse)
async def schedule_message(
    request: ScheduleRequest,
    api_key: APIKeyDep,
):
    """
    Schedule a message for sending.

    Messages are scheduled with a specific send time.
    The Celery task runner will pick them up and send at the scheduled time.
    """
    try:
        prospect_service = get_prospect_service()

        # Validate message exists
        message = await prospect_service.get_message(request.message_id)
        if not message:
            raise HTTPException(
                status_code=404,
                detail=f"Message not found: {request.message_id}"
            )

        # Check if already sent
        if message.get("status") == "sent":
            raise HTTPException(
                status_code=400,
                detail="Message has already been sent"
            )

        # Schedule the message
        result = await prospect_service.schedule_message(
            message_id=request.message_id,
            scheduled_time=request.scheduled_time,
            channel=request.channel,
        )

        logger.info(
            f"Scheduled message {request.message_id} for {request.scheduled_time}"
        )

        return ScheduleResponse(
            message_id=request.message_id,
            scheduled_time=request.scheduled_time,
            channel=request.channel,
            status="scheduled",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling message: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to schedule message: {str(e)}"
        )


@router.post("/schedule/batch", response_model=dict)
async def schedule_batch(
    campaign_id: int,
    channel: ChannelType,
    start_time: datetime | None = None,
    limit: int = Query(20, ge=1, le=50),
    api_key: APIKeyDep = None,
):
    """
    Schedule a batch of messages for a campaign.

    Messages are spread across the day with human-like timing.
    Respects daily quotas for each channel.
    """
    try:
        prospect_service = get_prospect_service()
        rate_limiter = get_outreach_rate_limiter()

        # Check quota
        allowed, remaining = await rate_limiter.check_quota(
            channel=channel if channel != "both" else "linkedin_connection",
            campaign_id=campaign_id,
        )

        if not allowed or remaining == 0:
            return {
                "status": "quota_exceeded",
                "message": f"Daily quota exceeded for {channel}",
                "scheduled": 0,
            }

        # Limit to quota remaining
        batch_limit = min(limit, remaining)

        # Get messages ready to schedule
        messages = await prospect_service.get_messages_for_scheduling(
            campaign_id=campaign_id,
            channel=channel,
            limit=batch_limit,
        )

        if not messages:
            return {
                "status": "no_messages",
                "message": "No messages ready for scheduling",
                "scheduled": 0,
            }

        # Schedule with staggered timing
        scheduled_count = await prospect_service.schedule_batch(
            messages=messages,
            start_time=start_time or datetime.utcnow(),
            channel=channel,
        )

        logger.info(
            f"Scheduled {scheduled_count} messages for campaign {campaign_id}"
        )

        return {
            "status": "scheduled",
            "campaign_id": campaign_id,
            "channel": channel,
            "scheduled": scheduled_count,
            "remaining_quota": remaining - scheduled_count,
        }

    except Exception as e:
        logger.error(f"Error scheduling batch: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to schedule batch: {str(e)}"
        )


# =============================================================================
# Direct Send Endpoints
# =============================================================================


@router.post("/send", response_model=SendResponse)
async def send_message(
    request: SendRequest,
    background_tasks: BackgroundTasks,
    api_key: APIKeyDep,
):
    """
    Send a message immediately.

    Bypasses scheduling and sends the message right away.
    Use with caution to respect rate limits.
    """
    try:
        prospect_service = get_prospect_service()
        rate_limiter = get_outreach_rate_limiter()

        # Get message
        message = await prospect_service.get_message(request.message_id)
        if not message:
            raise HTTPException(
                status_code=404,
                detail=f"Message not found: {request.message_id}"
            )

        if message.get("status") == "sent":
            raise HTTPException(
                status_code=400,
                detail="Message has already been sent"
            )

        # Check quota
        campaign_id = message.get("campaign_id", 1)
        channel_key = (
            "linkedin_connection"
            if request.channel == "linkedin"
            else "email"
        )

        allowed, remaining = await rate_limiter.check_quota(
            channel=channel_key,
            campaign_id=campaign_id,
        )

        if not allowed or remaining == 0:
            raise HTTPException(
                status_code=429,
                detail=f"Daily quota exceeded for {request.channel}"
            )

        # Queue the send task
        from ..tasks.outreach_tasks import (
            send_linkedin_connection_task,
            send_email_task,
        )

        if request.channel == "linkedin":
            send_linkedin_connection_task.delay(
                message_id=request.message_id,
                prospect_id=message.get("prospect_id"),
            )
        else:
            send_email_task.delay(
                message_id=request.message_id,
                prospect_id=message.get("prospect_id"),
            )

        # Update message status
        await prospect_service.update_message(
            request.message_id,
            {"status": "sending"}
        )

        logger.info(
            f"Queued message {request.message_id} for immediate send via {request.channel}"
        )

        return SendResponse(
            message_id=request.message_id,
            channel=request.channel,
            status="queued",
            queued_at=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send message: {str(e)}"
        )


@router.post("/send/batch")
async def send_batch(
    campaign_id: int,
    channel: ChannelType,
    background_tasks: BackgroundTasks,
    api_key: APIKeyDep,
):
    """
    Send all scheduled messages that are due.

    Processes scheduled messages and queues them for sending.
    """
    try:
        prospect_service = get_prospect_service()

        # Get due messages
        messages = await prospect_service.get_due_messages(
            campaign_id=campaign_id,
            channel=channel,
        )

        if not messages:
            return {
                "status": "no_messages",
                "message": "No messages due for sending",
                "sent": 0,
            }

        # Import and dispatch tasks
        from ..tasks.outreach_tasks import (
            dispatch_linkedin_batch_task,
            dispatch_email_batch_task,
        )

        message_ids = [m["id"] for m in messages]
        prospect_ids = [m["prospect_id"] for m in messages]

        if channel == "linkedin":
            dispatch_linkedin_batch_task.delay(
                message_ids=message_ids,
                prospect_ids=prospect_ids,
                campaign_id=campaign_id,
            )
        else:
            dispatch_email_batch_task.delay(
                message_ids=message_ids,
                prospect_ids=prospect_ids,
                campaign_id=campaign_id,
            )

        logger.info(
            f"Dispatched {len(messages)} {channel} messages for campaign {campaign_id}"
        )

        return {
            "status": "dispatched",
            "campaign_id": campaign_id,
            "channel": channel,
            "sent": len(messages),
        }

    except Exception as e:
        logger.error(f"Error sending batch: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send batch: {str(e)}"
        )


# =============================================================================
# Webhook Endpoints
# =============================================================================


@router.post("/webhooks/sendgrid")
async def sendgrid_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Process SendGrid webhook events.

    Handles email engagement events:
    - delivered, open, click, bounce, unsubscribe, spam_report
    """
    try:
        events = await request.json()

        if not isinstance(events, list):
            events = [events]

        # Queue processing
        from ..tasks.outreach_tasks import process_engagement_webhook_task

        for event in events:
            event_type = event.get("event", "unknown")
            background_tasks.add_task(
                lambda e=event, t=event_type: process_engagement_webhook_task.delay(
                    event_type=f"email_{t}",
                    payload=e,
                )
            )

        logger.info(f"Received {len(events)} SendGrid webhook events")

        return {"status": "accepted", "events": len(events)}

    except Exception as e:
        logger.error(f"Error processing SendGrid webhook: {e}")
        # Return 200 to prevent retries
        return {"status": "error", "message": str(e)}


@router.post("/webhooks/engagement")
async def engagement_webhook(
    event_type: str,
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
):
    """
    Generic engagement webhook endpoint.

    Accepts engagement events from various sources.
    """
    try:
        from ..tasks.outreach_tasks import process_engagement_webhook_task

        background_tasks.add_task(
            lambda: process_engagement_webhook_task.delay(
                event_type=event_type,
                payload=payload,
            )
        )

        logger.info(f"Received engagement event: {event_type}")

        return {"status": "accepted", "event_type": event_type}

    except Exception as e:
        logger.error(f"Error processing engagement webhook: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process webhook: {str(e)}"
        )


# =============================================================================
# Quota & Status Endpoints
# =============================================================================


@router.get("/quota/{campaign_id}", response_model=QuotaStatus)
async def get_quota_status(campaign_id: int):
    """
    Get current quota status for a campaign.

    Returns usage and remaining quota for each channel.
    """
    try:
        rate_limiter = get_outreach_rate_limiter()
        status = await rate_limiter.get_quota_status(campaign_id)

        return QuotaStatus(**status)

    except Exception as e:
        logger.error(f"Error getting quota status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics", response_model=AnalyticsDashboard)
async def get_analytics_dashboard(
    campaign_id: int | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
):
    """
    Get outreach analytics dashboard.

    Returns aggregated stats on messages, engagement, and conversions.
    """
    try:
        prospect_service = get_prospect_service()
        analytics = await prospect_service.get_analytics_dashboard(
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date,
        )

        return AnalyticsDashboard(**analytics)

    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/engagement-by-channel")
async def get_engagement_by_channel(
    campaign_id: int | None = Query(None),
    days: int = Query(30, ge=1, le=90),
):
    """
    Get engagement stats broken down by channel.
    """
    try:
        prospect_service = get_prospect_service()
        stats = await prospect_service.get_engagement_by_channel(
            campaign_id=campaign_id,
            days=days,
        )

        return stats

    except Exception as e:
        logger.error(f"Error getting channel engagement: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics/daily-stats")
async def get_daily_stats(
    campaign_id: int | None = Query(None),
    days: int = Query(14, ge=1, le=30),
):
    """
    Get daily outreach statistics.

    Returns day-by-day breakdown of sends, opens, clicks, replies.
    """
    try:
        prospect_service = get_prospect_service()
        stats = await prospect_service.get_daily_stats(
            campaign_id=campaign_id,
            days=days,
        )

        return {"days": stats}

    except Exception as e:
        logger.error(f"Error getting daily stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Status Check Endpoints
# =============================================================================


@router.get("/status/linkedin")
async def check_linkedin_status():
    """
    Check LinkedIn service status.

    Verifies browser automation is working and session is valid.
    """
    try:
        from ..services.linkedin_service import get_linkedin_service

        service = get_linkedin_service()
        initialized = await service.initialize()

        if initialized:
            await service.close()
            return {
                "status": "ok",
                "message": "LinkedIn service is operational",
            }
        else:
            return {
                "status": "error",
                "message": "LinkedIn session invalid. Please update cookies.",
            }

    except Exception as e:
        logger.error(f"LinkedIn status check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


@router.get("/status/email")
async def check_email_status():
    """
    Check email service status.

    Verifies SendGrid API is configured and accessible.
    """
    try:
        from ..services.email_service import get_email_service

        service = get_email_service()

        if service.api_key:
            return {
                "status": "ok",
                "message": "Email service is configured",
                "from_email": service.from_email,
            }
        else:
            return {
                "status": "error",
                "message": "SendGrid API key not configured",
            }

    except Exception as e:
        logger.error(f"Email status check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


@router.post("/trigger/daily-batch")
async def trigger_daily_batch(
    campaign_id: int,
    api_key: APIKeyDep,
):
    """
    Manually trigger daily batch scheduling.

    Normally runs automatically via Celery Beat.
    Use for testing or catch-up.
    """
    try:
        from ..tasks.outreach_tasks import schedule_daily_batch_task

        result = schedule_daily_batch_task.delay(campaign_id)

        return {
            "status": "triggered",
            "task_id": result.id,
            "campaign_id": campaign_id,
        }

    except Exception as e:
        logger.error(f"Error triggering daily batch: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger batch: {str(e)}"
        )


@router.post("/trigger/followups")
async def trigger_followups(
    campaign_id: int,
    api_key: APIKeyDep,
):
    """
    Manually trigger follow-up scheduling.

    Checks for prospects needing follow-up and schedules messages.
    """
    try:
        from ..tasks.outreach_tasks import schedule_followups_task

        result = schedule_followups_task.delay(campaign_id)

        return {
            "status": "triggered",
            "task_id": result.id,
            "campaign_id": campaign_id,
        }

    except Exception as e:
        logger.error(f"Error triggering followups: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger followups: {str(e)}"
        )
