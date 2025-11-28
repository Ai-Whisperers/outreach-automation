"""
Reply Detection Service.

Handles inbound email parsing and reply detection via SendGrid Inbound Parse.
When a prospect replies, this service:
1. Matches the reply to the original prospect
2. Updates prospect status to REPLIED
3. Cancels all pending follow-up messages
4. Creates engagement event
5. Optionally notifies campaign owner
"""

import email
import re
from datetime import datetime
from email.utils import parseaddr
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

logger = get_logger("services.reply_detection")


class ReplyDetectionService:
    """
    Detect and process email replies from prospects.

    Uses SendGrid Inbound Parse webhook to receive replies.
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def process_inbound_email(
        self,
        from_email: str,
        from_name: str | None,
        to_email: str,
        subject: str,
        text_body: str | None,
        html_body: str | None,
        headers: dict[str, str] | None = None,
        attachments: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Process an inbound email from SendGrid Inbound Parse.

        Args:
            from_email: Sender's email address
            from_name: Sender's name
            to_email: Recipient email (our reply-to address)
            subject: Email subject
            text_body: Plain text body
            html_body: HTML body
            headers: Email headers (for threading)
            attachments: List of attachment info

        Returns:
            Processing result with matched prospect info
        """
        result = {
            "processed": False,
            "matched": False,
            "prospect_id": None,
            "message_id": None,
            "action_taken": None,
        }

        try:
            # Clean the from_email
            _, clean_email = parseaddr(from_email)
            clean_email = clean_email.lower().strip()

            if not clean_email:
                logger.warning("Invalid from_email in inbound message")
                return result

            # Try to match to a prospect
            prospect = await self._find_prospect_by_email(clean_email)

            if not prospect:
                logger.info(f"No prospect found for email: {clean_email}")
                # Store as unmatched inbound for manual review
                await self._store_unmatched_inbound(
                    from_email=clean_email,
                    from_name=from_name,
                    subject=subject,
                    text_body=text_body,
                    headers=headers,
                )
                result["processed"] = True
                return result

            result["matched"] = True
            result["prospect_id"] = prospect.id

            # Find the original message (if possible via threading)
            original_message = await self._find_original_message(
                prospect_id=prospect.id,
                subject=subject,
                headers=headers,
            )

            if original_message:
                result["message_id"] = original_message.id

            # Process the reply
            await self._process_reply(
                prospect=prospect,
                original_message=original_message,
                reply_subject=subject,
                reply_body=text_body or self._html_to_text(html_body or ""),
            )

            result["processed"] = True
            result["action_taken"] = "prospect_marked_replied_sequence_paused"

            logger.info(
                f"Reply processed: prospect_id={prospect.id}, "
                f"original_message_id={original_message.id if original_message else 'unknown'}"
            )

            return result

        except Exception as e:
            logger.error(f"Error processing inbound email: {e}")
            result["error"] = str(e)
            return result

    async def _find_prospect_by_email(self, email: str) -> Prospect | None:
        """Find prospect by email address."""
        stmt = select(Prospect).where(Prospect.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_original_message(
        self,
        prospect_id: int,
        subject: str,
        headers: dict[str, str] | None,
    ) -> OutreachMessage | None:
        """
        Try to find the original outbound message this is a reply to.

        Uses multiple strategies:
        1. In-Reply-To header matching
        2. References header matching
        3. Subject line matching (fallback)
        """
        # Strategy 1: In-Reply-To header
        if headers:
            in_reply_to = headers.get("In-Reply-To", "").strip("<>")
            if in_reply_to:
                stmt = select(OutreachMessage).where(
                    OutreachMessage.prospect_id == prospect_id,
                    OutreachMessage.external_message_id == in_reply_to,
                )
                result = await self.db.execute(stmt)
                message = result.scalar_one_or_none()
                if message:
                    return message

            # Strategy 2: References header
            references = headers.get("References", "")
            if references:
                # References can contain multiple message IDs
                ref_ids = re.findall(r"<([^>]+)>", references)
                for ref_id in ref_ids:
                    stmt = select(OutreachMessage).where(
                        OutreachMessage.prospect_id == prospect_id,
                        OutreachMessage.external_message_id == ref_id,
                    )
                    result = await self.db.execute(stmt)
                    message = result.scalar_one_or_none()
                    if message:
                        return message

        # Strategy 3: Subject line matching (remove Re:, Fwd:, etc.)
        clean_subject = self._clean_subject(subject)
        if clean_subject:
            stmt = select(OutreachMessage).where(
                OutreachMessage.prospect_id == prospect_id,
                OutreachMessage.subject.ilike(f"%{clean_subject}%"),
                OutreachMessage.status == MessageStatus.SENT,
            ).order_by(OutreachMessage.sent_at.desc())
            result = await self.db.execute(stmt)
            message = result.scalars().first()
            if message:
                return message

        # Fallback: Just get the most recent sent message to this prospect
        stmt = select(OutreachMessage).where(
            OutreachMessage.prospect_id == prospect_id,
            OutreachMessage.status == MessageStatus.SENT,
        ).order_by(OutreachMessage.sent_at.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _process_reply(
        self,
        prospect: Prospect,
        original_message: OutreachMessage | None,
        reply_subject: str,
        reply_body: str,
    ):
        """
        Process a confirmed reply from a prospect.

        Updates:
        1. Prospect status → REPLIED
        2. Sequence paused
        3. Cancel pending messages
        4. Create engagement event
        5. Analyze sentiment (optional)
        """
        # 1. Update prospect status
        prospect.status = ProspectStatus.REPLIED
        prospect.sequence_paused = True
        prospect.sequence_paused_reason = "Prospect replied"
        prospect.updated_at = datetime.utcnow()

        # Simple sentiment detection
        sentiment = self._detect_basic_sentiment(reply_body)
        prospect.reply_sentiment = sentiment

        # 2. Cancel all pending follow-up messages
        await self._cancel_pending_messages(prospect.id)

        # 3. Create engagement event
        event = EngagementEvent(
            prospect_id=prospect.id,
            message_id=original_message.id if original_message else None,
            event_type="reply",
            channel=OutreachChannel.EMAIL,
            metadata={
                "subject": reply_subject[:200],
                "body_preview": reply_body[:500] if reply_body else None,
                "sentiment": sentiment,
                "original_message_type": original_message.message_type.value if original_message else None,
            },
            occurred_at=datetime.utcnow(),
        )
        self.db.add(event)

        # 4. Commit changes
        await self.db.commit()

        logger.info(
            f"Reply processed for prospect {prospect.id}: "
            f"sentiment={sentiment}, sequence paused"
        )

    async def _cancel_pending_messages(self, prospect_id: int):
        """Cancel all pending/scheduled messages for a prospect."""
        stmt = (
            update(OutreachMessage)
            .where(OutreachMessage.prospect_id == prospect_id)
            .where(
                OutreachMessage.status.in_([
                    MessageStatus.DRAFT,
                    MessageStatus.APPROVED,
                    MessageStatus.SCHEDULED,
                ])
            )
            .values(status=MessageStatus.CANCELLED)
        )
        result = await self.db.execute(stmt)
        cancelled_count = result.rowcount

        if cancelled_count > 0:
            logger.info(f"Cancelled {cancelled_count} pending messages for prospect {prospect_id}")

    async def _store_unmatched_inbound(
        self,
        from_email: str,
        from_name: str | None,
        subject: str,
        text_body: str | None,
        headers: dict | None,
    ):
        """Store unmatched inbound email for manual review."""
        # This would insert into inbound_emails table
        # For now, just log it
        logger.info(
            f"Unmatched inbound email: from={from_email}, subject={subject[:50]}"
        )

    def _clean_subject(self, subject: str) -> str:
        """Remove Re:, Fwd:, etc. from subject line."""
        if not subject:
            return ""
        # Remove common prefixes
        cleaned = re.sub(
            r"^(re|fwd|fw|aw|sv|vs|ref|rif|r|tr|wg|enc|rv):\s*",
            "",
            subject,
            flags=re.IGNORECASE,
        )
        # Remove [EXT], [EXTERNAL], etc.
        cleaned = re.sub(r"\[(?:ext(?:ernal)?|spam)\]\s*", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def _html_to_text(self, html: str) -> str:
        """Simple HTML to text conversion."""
        if not html:
            return ""
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Convert entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        # Clean whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _detect_basic_sentiment(self, text: str) -> str:
        """
        Basic sentiment detection for reply.

        Returns: positive, negative, neutral, or interested
        """
        if not text:
            return "neutral"

        text_lower = text.lower()

        # Positive indicators
        positive_words = [
            "interested", "sounds great", "let's chat", "let's talk",
            "schedule", "meeting", "call", "demo", "learn more",
            "tell me more", "yes", "love to", "would like",
            "available", "free time", "calendar",
        ]

        # Negative indicators
        negative_words = [
            "not interested", "no thanks", "unsubscribe", "remove",
            "stop", "don't contact", "not for us", "wrong person",
            "not the right", "busy", "not now", "maybe later",
            "pass", "decline",
        ]

        # Check for positive signals (interest in meeting/learning more)
        for word in positive_words:
            if word in text_lower:
                return "interested"

        # Check for negative signals
        for word in negative_words:
            if word in text_lower:
                return "negative"

        # Default to neutral (need human review)
        return "neutral"


# =============================================================================
# Parse SendGrid Inbound Parse Webhook
# =============================================================================


def parse_inbound_parse_webhook(form_data: dict) -> dict[str, Any]:
    """
    Parse SendGrid Inbound Parse webhook form data.

    SendGrid sends multipart/form-data with these fields:
    - from: Sender email
    - to: Recipient email
    - subject: Email subject
    - text: Plain text body
    - html: HTML body
    - headers: Raw email headers
    - envelope: JSON with to/from
    - attachments: Number of attachments
    - attachment-info: JSON with attachment details
    - attachment1, attachment2, etc.: Actual attachment files

    Returns:
        Parsed email data dict
    """
    # Parse the 'from' field
    from_raw = form_data.get("from", "")
    from_name, from_email = parseaddr(from_raw)

    # Parse headers if present
    headers = {}
    headers_raw = form_data.get("headers", "")
    if headers_raw:
        try:
            parsed = email.message_from_string(headers_raw)
            headers = dict(parsed.items())
        except Exception:
            pass

    return {
        "from_email": from_email,
        "from_name": from_name,
        "to_email": form_data.get("to", ""),
        "subject": form_data.get("subject", ""),
        "text_body": form_data.get("text"),
        "html_body": form_data.get("html"),
        "headers": headers,
        "envelope": form_data.get("envelope"),
        "attachment_count": int(form_data.get("attachments", 0)),
    }


# =============================================================================
# Factory Function
# =============================================================================


def get_reply_detection_service(db_session: AsyncSession) -> ReplyDetectionService:
    """Factory function to get ReplyDetectionService instance."""
    return ReplyDetectionService(db_session)
