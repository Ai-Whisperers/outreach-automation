"""
Webhook Routes.

Consolidated webhook endpoints for:
- SendGrid event webhooks (delivered, opened, clicked, bounced, etc.)
- SendGrid Inbound Parse (reply detection)
"""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request

from ..logging_config import get_logger
from ..services.webhook_processor import WebhookProcessor, verify_sendgrid_signature
from ..services.reply_detection_service import (
    ReplyDetectionService,
    parse_inbound_parse_webhook,
)
from ..database.engine import get_db_session

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger("routes.webhooks")


# =============================================================================
# SendGrid Event Webhook
# =============================================================================


@router.post("/sendgrid/events")
async def sendgrid_event_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Process SendGrid event webhooks.

    SendGrid sends events for:
    - delivered: Email delivered to recipient server
    - open: Email opened (tracking pixel loaded)
    - click: Link clicked in email
    - bounce: Email bounced (hard or soft)
    - dropped: Email dropped by SendGrid
    - spam_report: Recipient marked as spam
    - unsubscribe: Recipient unsubscribed
    - deferred: Temporary delivery failure

    These events update our database to track engagement.
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Get signature headers (optional but recommended)
        signature = request.headers.get("X-Twilio-Email-Event-Webhook-Signature")
        timestamp = request.headers.get("X-Twilio-Email-Event-Webhook-Timestamp")

        # Parse events
        events = await request.json()

        if not isinstance(events, list):
            events = [events]

        logger.info(f"Received {len(events)} SendGrid events")

        # Process in background to return quickly (SendGrid expects fast response)
        background_tasks.add_task(
            process_sendgrid_events_background,
            events=events,
            signature=signature,
            timestamp=timestamp,
        )

        return {"status": "accepted", "events_received": len(events)}

    except Exception as e:
        logger.error(f"Error receiving SendGrid webhook: {e}")
        # Return 200 to prevent SendGrid retries for bad data
        return {"status": "error", "message": str(e)}


async def process_sendgrid_events_background(
    events: list[dict],
    signature: str | None,
    timestamp: str | None,
):
    """Background task to process SendGrid events."""
    try:
        async with get_db_session() as db:
            processor = WebhookProcessor(db)
            result = await processor.process_sendgrid_events(
                events=events,
                signature=signature,
                timestamp=timestamp,
            )
            logger.info(f"Processed SendGrid events: {result}")

    except Exception as e:
        logger.error(f"Error processing SendGrid events: {e}")


# =============================================================================
# SendGrid Inbound Parse (Reply Detection)
# =============================================================================


@router.post("/sendgrid/inbound")
async def sendgrid_inbound_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Process SendGrid Inbound Parse webhooks for reply detection.

    When a prospect replies to our outreach email, SendGrid forwards
    the reply to this endpoint. We then:
    1. Match the reply to the original prospect
    2. Update prospect status to REPLIED
    3. Cancel pending follow-up messages
    4. Create engagement event

    SendGrid sends this as multipart/form-data with fields:
    - from: Sender email/name
    - to: Our reply-to address
    - subject: Email subject
    - text: Plain text body
    - html: HTML body
    - headers: Raw email headers
    - envelope: JSON with routing info
    - attachments: Number of attachments
    """
    try:
        # Parse form data
        form_data = await request.form()
        form_dict = dict(form_data)

        logger.info(
            f"Received inbound email from: {form_dict.get('from', 'unknown')}"
        )

        # Parse into structured data
        email_data = parse_inbound_parse_webhook(form_dict)

        # Process in background
        background_tasks.add_task(
            process_inbound_email_background,
            email_data=email_data,
        )

        return {"status": "accepted"}

    except Exception as e:
        logger.error(f"Error receiving inbound webhook: {e}")
        return {"status": "error", "message": str(e)}


async def process_inbound_email_background(email_data: dict):
    """Background task to process inbound email (reply)."""
    try:
        async with get_db_session() as db:
            service = ReplyDetectionService(db)
            result = await service.process_inbound_email(
                from_email=email_data["from_email"],
                from_name=email_data.get("from_name"),
                to_email=email_data["to_email"],
                subject=email_data["subject"],
                text_body=email_data.get("text_body"),
                html_body=email_data.get("html_body"),
                headers=email_data.get("headers"),
            )

            if result["matched"]:
                logger.info(
                    f"Reply processed: prospect_id={result['prospect_id']}, "
                    f"action={result['action_taken']}"
                )
            else:
                logger.info(f"Inbound email not matched to prospect: {email_data['from_email']}")

    except Exception as e:
        logger.error(f"Error processing inbound email: {e}")


# =============================================================================
# Health Check
# =============================================================================


@router.get("/health")
async def webhook_health():
    """Health check for webhook endpoints."""
    return {
        "status": "ok",
        "endpoints": {
            "sendgrid_events": "/webhooks/sendgrid/events",
            "sendgrid_inbound": "/webhooks/sendgrid/inbound",
        },
    }


# =============================================================================
# Test Endpoints (for development)
# =============================================================================


@router.post("/test/event")
async def test_event_webhook(event_type: str, tracking_id: str):
    """
    Test endpoint to simulate a SendGrid event.

    For development/testing only.
    """
    test_event = {
        "event": event_type,
        "tracking_id": tracking_id,
        "timestamp": 1234567890,
        "sg_event_id": "test_event_123",
    }

    try:
        async with get_db_session() as db:
            processor = WebhookProcessor(db)
            result = await processor.process_sendgrid_events([test_event])
            return {"status": "processed", "result": result}

    except Exception as e:
        logger.error(f"Test event error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/reply")
async def test_reply_webhook(
    from_email: str,
    subject: str = "Re: Test Email",
    body: str = "Thanks for reaching out!",
):
    """
    Test endpoint to simulate an inbound reply.

    For development/testing only.
    """
    try:
        async with get_db_session() as db:
            service = ReplyDetectionService(db)
            result = await service.process_inbound_email(
                from_email=from_email,
                from_name=None,
                to_email="reply@ai-whisperers.com",
                subject=subject,
                text_body=body,
                html_body=None,
            )
            return {"status": "processed", "result": result}

    except Exception as e:
        logger.error(f"Test reply error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
