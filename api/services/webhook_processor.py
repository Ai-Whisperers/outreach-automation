"""
Webhook Processor Service.

Handles SendGrid webhook events and updates database accordingly.
This is the core of Phase 1.1 - fixing webhook processing to actually update the DB.
"""

import hashlib
import hmac
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.outreach_models import (
    EngagementEvent,
    MessageStatus,
    OutreachChannel,
    OutreachMessage,
    Prospect,
    ProspectStatus,
)
from ..logging_config import get_logger

logger = get_logger("services.webhook_processor")


class WebhookProcessor:
    """
    Process SendGrid webhooks and update database.

    Handles:
    - delivered: Mark message as delivered
    - open: Track opens, update prospect to engaged
    - click: Track clicks, update engagement score
    - bounce: Mark prospect as bounced, cancel sequence
    - spam_report: Mark prospect as complained
    - unsubscribe: Mark prospect as opted out
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def process_sendgrid_events(
        self,
        events: list[dict[str, Any]],
        signature: str | None = None,
        timestamp: str | None = None,
    ) -> dict[str, int]:
        """
        Process a batch of SendGrid webhook events.

        Args:
            events: List of SendGrid event objects
            signature: SendGrid webhook signature for verification
            timestamp: SendGrid webhook timestamp

        Returns:
            Dict with counts per event type
        """
        counts = {
            "processed": 0,
            "delivered": 0,
            "open": 0,
            "click": 0,
            "bounce": 0,
            "spam_report": 0,
            "unsubscribe": 0,
            "dropped": 0,
            "deferred": 0,
            "errors": 0,
        }

        for event in events:
            try:
                event_type = event.get("event", "unknown")
                counts["processed"] += 1

                # Extract tracking ID (our message ID)
                tracking_id = self._extract_tracking_id(event)

                if not tracking_id:
                    logger.warning(f"No tracking_id in event: {event_type}")
                    continue

                # Process based on event type
                handler = getattr(self, f"_handle_{event_type}", None)
                if handler:
                    await handler(tracking_id, event)
                    counts[event_type] = counts.get(event_type, 0) + 1
                else:
                    logger.debug(f"Unhandled event type: {event_type}")

            except Exception as e:
                logger.error(f"Error processing event: {e}")
                counts["errors"] += 1

        # Commit all changes
        await self.db.commit()

        logger.info(f"Webhook processing complete: {counts}")
        return counts

    def _extract_tracking_id(self, event: dict) -> str | None:
        """Extract our message tracking ID from SendGrid event."""
        # Check custom_args first (our preferred method)
        custom_args = event.get("custom_args", {})
        if "tracking_id" in custom_args:
            return custom_args["tracking_id"]

        # Check sg_message_id
        if "sg_message_id" in event:
            return event["sg_message_id"].split(".")[0]

        # Check for our tracking_id in various locations
        for key in ["tracking_id", "message_id", "smtp-id"]:
            if key in event:
                return event[key]

        return None

    # =========================================================================
    # Event Handlers
    # =========================================================================

    async def _handle_delivered(self, tracking_id: str, event: dict):
        """Handle email delivered event."""
        message = await self._get_message(tracking_id)
        if not message:
            return

        # Update message
        message.status = MessageStatus.SENT
        message.delivered_at = datetime.utcnow()
        message.external_message_id = event.get("sg_message_id")

        # Create engagement event
        await self._create_engagement_event(
            prospect_id=message.prospect_id,
            message_id=message.id,
            event_type="delivered",
            metadata={"sg_event_id": event.get("sg_event_id")},
        )

        logger.info(f"Email delivered: message_id={message.id}")

    async def _handle_open(self, tracking_id: str, event: dict):
        """Handle email open event."""
        message = await self._get_message(tracking_id)
        if not message:
            return

        now = datetime.utcnow()

        # Update message (only first open time, but increment count)
        if not message.opened_at:
            message.opened_at = now
        message.open_count = (message.open_count or 0) + 1

        # Update prospect status to engaged if not already replied/converted
        prospect = await self._get_prospect(message.prospect_id)
        if prospect and prospect.status in [
            ProspectStatus.CONTACTED,
            ProspectStatus.SCHEDULED,
        ]:
            prospect.status = ProspectStatus.ENGAGED
            prospect.engagement_score = (prospect.engagement_score or 0) + 1

        # Create engagement event
        await self._create_engagement_event(
            prospect_id=message.prospect_id,
            message_id=message.id,
            event_type="open",
            metadata={
                "ip": event.get("ip"),
                "user_agent": event.get("useragent"),
                "sg_event_id": event.get("sg_event_id"),
            },
        )

        logger.info(f"Email opened: message_id={message.id}, count={message.open_count}")

    async def _handle_click(self, tracking_id: str, event: dict):
        """Handle email click event."""
        message = await self._get_message(tracking_id)
        if not message:
            return

        now = datetime.utcnow()

        # Update message
        if not message.clicked_at:
            message.clicked_at = now
        message.click_count = (message.click_count or 0) + 1

        # Update prospect engagement score
        prospect = await self._get_prospect(message.prospect_id)
        if prospect:
            if prospect.status in [
                ProspectStatus.CONTACTED,
                ProspectStatus.SCHEDULED,
            ]:
                prospect.status = ProspectStatus.ENGAGED
            prospect.engagement_score = (prospect.engagement_score or 0) + 2  # Clicks worth more

        # Create engagement event
        await self._create_engagement_event(
            prospect_id=message.prospect_id,
            message_id=message.id,
            event_type="click",
            metadata={
                "url": event.get("url"),
                "ip": event.get("ip"),
                "user_agent": event.get("useragent"),
            },
        )

        logger.info(f"Email clicked: message_id={message.id}, url={event.get('url')}")

    async def _handle_bounce(self, tracking_id: str, event: dict):
        """Handle email bounce event."""
        message = await self._get_message(tracking_id)
        if not message:
            return

        bounce_type = event.get("type", "unknown")  # hard, soft, blocked
        reason = event.get("reason", "")

        # Update message
        message.status = MessageStatus.FAILED
        message.bounced_at = datetime.utcnow()
        message.bounce_type = bounce_type
        message.error_message = reason[:500] if reason else None

        # Update prospect
        prospect = await self._get_prospect(message.prospect_id)
        if prospect:
            # Hard bounces = invalid email
            if bounce_type == "hard":
                prospect.status = ProspectStatus.BOUNCED
                prospect.email_status = "bounced"
                prospect.sequence_paused = True
                prospect.sequence_paused_reason = f"Hard bounce: {reason[:100]}"
            else:
                # Soft bounces might be temporary
                prospect.email_status = "soft_bounced"

        # Cancel pending follow-ups
        await self._cancel_pending_messages(message.prospect_id)

        # Create engagement event
        await self._create_engagement_event(
            prospect_id=message.prospect_id,
            message_id=message.id,
            event_type="bounce",
            metadata={
                "bounce_type": bounce_type,
                "reason": reason,
                "status": event.get("status"),
            },
        )

        logger.warning(f"Email bounced ({bounce_type}): message_id={message.id}, reason={reason[:100]}")

    async def _handle_spam_report(self, tracking_id: str, event: dict):
        """Handle spam report event - CRITICAL."""
        message = await self._get_message(tracking_id)
        if not message:
            return

        # Update prospect - immediate opt-out
        prospect = await self._get_prospect(message.prospect_id)
        if prospect:
            prospect.status = ProspectStatus.OPTED_OUT
            prospect.email_status = "complained"
            prospect.sequence_paused = True
            prospect.sequence_paused_reason = "Spam report received"

        # Cancel ALL pending messages
        await self._cancel_pending_messages(message.prospect_id)

        # Create engagement event
        await self._create_engagement_event(
            prospect_id=message.prospect_id,
            message_id=message.id,
            event_type="spam_report",
            metadata={"sg_event_id": event.get("sg_event_id")},
        )

        logger.error(f"SPAM REPORT: message_id={message.id}, prospect_id={message.prospect_id}")

    async def _handle_unsubscribe(self, tracking_id: str, event: dict):
        """Handle unsubscribe event."""
        message = await self._get_message(tracking_id)
        if not message:
            return

        # Update prospect
        prospect = await self._get_prospect(message.prospect_id)
        if prospect:
            prospect.status = ProspectStatus.OPTED_OUT
            prospect.email_status = "unsubscribed"
            prospect.sequence_paused = True
            prospect.sequence_paused_reason = "User unsubscribed"

        # Cancel pending messages
        await self._cancel_pending_messages(message.prospect_id)

        # Create engagement event
        await self._create_engagement_event(
            prospect_id=message.prospect_id,
            message_id=message.id,
            event_type="unsubscribe",
            metadata={"sg_event_id": event.get("sg_event_id")},
        )

        logger.info(f"Unsubscribe: message_id={message.id}, prospect_id={message.prospect_id}")

    async def _handle_dropped(self, tracking_id: str, event: dict):
        """Handle dropped event (email not sent)."""
        message = await self._get_message(tracking_id)
        if not message:
            return

        reason = event.get("reason", "unknown")

        message.status = MessageStatus.FAILED
        message.error_message = f"Dropped: {reason}"

        # Create engagement event
        await self._create_engagement_event(
            prospect_id=message.prospect_id,
            message_id=message.id,
            event_type="dropped",
            metadata={"reason": reason},
        )

        logger.warning(f"Email dropped: message_id={message.id}, reason={reason}")

    async def _handle_deferred(self, tracking_id: str, event: dict):
        """Handle deferred event (temporary delivery failure)."""
        message = await self._get_message(tracking_id)
        if not message:
            return

        # Just log for now - SendGrid will retry
        await self._create_engagement_event(
            prospect_id=message.prospect_id,
            message_id=message.id,
            event_type="deferred",
            metadata={
                "reason": event.get("reason"),
                "attempt": event.get("attempt"),
            },
        )

        logger.info(f"Email deferred: message_id={message.id}")

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _get_message(self, tracking_id: str) -> OutreachMessage | None:
        """Get message by tracking ID (our message ID)."""
        try:
            message_id = int(tracking_id)
        except (ValueError, TypeError):
            # Try to find by external_message_id
            stmt = select(OutreachMessage).where(
                OutreachMessage.external_message_id == tracking_id
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        stmt = select(OutreachMessage).where(OutreachMessage.id == message_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_prospect(self, prospect_id: int) -> Prospect | None:
        """Get prospect by ID."""
        stmt = select(Prospect).where(Prospect.id == prospect_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _create_engagement_event(
        self,
        prospect_id: int,
        message_id: int | None,
        event_type: str,
        metadata: dict | None = None,
    ):
        """Create an engagement event record."""
        event = EngagementEvent(
            prospect_id=prospect_id,
            message_id=message_id,
            event_type=event_type,
            channel=OutreachChannel.EMAIL,
            metadata=metadata,
            occurred_at=datetime.utcnow(),
        )
        self.db.add(event)

    async def _cancel_pending_messages(self, prospect_id: int):
        """Cancel all pending/scheduled messages for a prospect."""
        stmt = (
            update(OutreachMessage)
            .where(OutreachMessage.prospect_id == prospect_id)
            .where(OutreachMessage.status.in_([MessageStatus.DRAFT, MessageStatus.APPROVED, MessageStatus.SCHEDULED]))
            .values(status=MessageStatus.CANCELLED)
        )
        await self.db.execute(stmt)

        logger.info(f"Cancelled pending messages for prospect_id={prospect_id}")


# =============================================================================
# Signature Verification
# =============================================================================


def verify_sendgrid_signature(
    payload: bytes,
    signature: str,
    timestamp: str,
    webhook_key: str,
) -> bool:
    """
    Verify SendGrid webhook signature.

    Args:
        payload: Raw request body
        signature: X-Twilio-Email-Event-Webhook-Signature header
        timestamp: X-Twilio-Email-Event-Webhook-Timestamp header
        webhook_key: Your SendGrid webhook verification key

    Returns:
        True if signature is valid
    """
    if not all([payload, signature, timestamp, webhook_key]):
        return False

    try:
        # Concatenate timestamp and payload
        payload_to_sign = timestamp.encode() + payload

        # Create HMAC SHA256 signature
        expected_signature = hmac.new(
            webhook_key.encode(),
            payload_to_sign,
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison
        return hmac.compare_digest(signature, expected_signature)

    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False


# =============================================================================
# Factory Function
# =============================================================================


def get_webhook_processor(db_session: AsyncSession) -> WebhookProcessor:
    """Factory function to get WebhookProcessor instance."""
    return WebhookProcessor(db_session)
