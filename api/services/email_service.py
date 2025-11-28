"""
Email Service with SendGrid Integration.

Features:
- SendGrid API integration
- Email sending with tracking
- Open tracking (pixel)
- Click tracking (link wrapping)
- Unsubscribe handling
- Bounce processing
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger("services.email")


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class EmailResult:
    """Result of sending an email."""

    success: bool
    message_id: str | None = None
    error: str | None = None
    timestamp: datetime | None = None


@dataclass
class EmailConfig:
    """Email configuration."""

    from_email: str
    from_name: str
    tracking_domain: str | None = None
    reply_to: str | None = None


# =============================================================================
# Email Service
# =============================================================================


class EmailService:
    """
    SendGrid email service with tracking.

    Usage:
        service = EmailService()
        result = await service.send_email(
            to_email="recipient@example.com",
            subject="Hello",
            html_content="<p>Message body</p>",
            tracking_id="msg_123"
        )
    """

    def __init__(self):
        self.settings = get_settings()
        self.api_key = getattr(self.settings, "sendgrid_api_key", None)
        self.from_email = getattr(
            self.settings, "email_from_address", "hello@ai-whisperers.com"
        )
        self.from_name = getattr(self.settings, "email_from_name", "AI Whisperers")
        self.tracking_domain = getattr(self.settings, "email_tracking_domain", None)

        self.base_url = "https://api.sendgrid.com/v3"

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        tracking_id: str,
        text_content: str | None = None,
        reply_to: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        categories: list[str] | None = None,
    ) -> EmailResult:
        """
        Send an email via SendGrid with tracking enabled.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML body
            tracking_id: Unique ID for tracking (message ID from DB)
            text_content: Plain text body (optional, generated from HTML if not provided)
            reply_to: Reply-to address (optional)
            from_email: From email (optional, uses default)
            from_name: From name (optional, uses default)
            categories: SendGrid categories for analytics

        Returns:
            EmailResult with success status and message ID
        """
        if not self.api_key:
            logger.error("SendGrid API key not configured")
            return EmailResult(
                success=False,
                error="Email service not configured",
                timestamp=datetime.utcnow()
            )

        try:
            # Add tracking to content
            html_with_tracking = self._add_tracking(html_content, tracking_id)

            # Generate plain text if not provided
            if not text_content:
                text_content = self._html_to_text(html_content)

            # Build SendGrid payload
            payload = {
                "personalizations": [
                    {
                        "to": [{"email": to_email}],
                        "custom_args": {"tracking_id": tracking_id},
                    }
                ],
                "from": {
                    "email": from_email or self.from_email,
                    "name": from_name or self.from_name,
                },
                "subject": subject,
                "content": [
                    {"type": "text/plain", "value": text_content},
                    {"type": "text/html", "value": html_with_tracking},
                ],
                "tracking_settings": {
                    "click_tracking": {"enable": True, "enable_text": False},
                    "open_tracking": {"enable": True},
                },
            }

            # Add optional fields
            if reply_to:
                payload["reply_to"] = {"email": reply_to}

            if categories:
                payload["categories"] = categories

            # Send via SendGrid API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/mail/send",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30.0,
                )

                if response.status_code in [200, 201, 202]:
                    message_id = response.headers.get("X-Message-Id", tracking_id)
                    logger.info(f"Email sent successfully: {to_email} (ID: {message_id})")
                    return EmailResult(
                        success=True,
                        message_id=message_id,
                        timestamp=datetime.utcnow()
                    )
                else:
                    error_msg = f"SendGrid error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return EmailResult(
                        success=False,
                        error=error_msg,
                        timestamp=datetime.utcnow()
                    )

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return EmailResult(
                success=False,
                error=str(e),
                timestamp=datetime.utcnow()
            )

    async def send_batch(
        self,
        emails: list[dict[str, Any]],
    ) -> list[EmailResult]:
        """
        Send multiple emails (uses SendGrid batch API if available).

        Args:
            emails: List of email dicts with to_email, subject, html_content, tracking_id

        Returns:
            List of EmailResult for each email
        """
        results = []
        for email_data in emails:
            result = await self.send_email(**email_data)
            results.append(result)
        return results

    async def send_batch_v2(
        self,
        emails: list[dict[str, Any]],
        batch_size: int = 1000,
    ) -> dict[str, Any]:
        """
        Send multiple emails using SendGrid's true batch API with personalizations.

        This is much more efficient than sequential sending:
        - Single API call for up to 1000 recipients
        - Each recipient gets personalized content
        - Atomic operation

        Args:
            emails: List of email dicts with:
                - to_email: recipient email
                - to_name: recipient name (optional)
                - subject: email subject
                - html_content: HTML body
                - text_content: plain text body (optional)
                - tracking_id: our message ID for tracking
                - merge_fields: dict of personalization variables (optional)
            batch_size: Max emails per API call (SendGrid limit is 1000)

        Returns:
            Dict with success count, failed count, and details
        """
        if not self.api_key:
            logger.error("SendGrid API key not configured")
            return {
                "success": False,
                "error": "Email service not configured",
                "sent": 0,
                "failed": len(emails),
            }

        results = {
            "success": True,
            "sent": 0,
            "failed": 0,
            "errors": [],
            "message_ids": [],
        }

        # Process in batches
        for i in range(0, len(emails), batch_size):
            batch = emails[i : i + batch_size]
            batch_result = await self._send_single_batch(batch)

            results["sent"] += batch_result["sent"]
            results["failed"] += batch_result["failed"]
            results["errors"].extend(batch_result.get("errors", []))
            results["message_ids"].extend(batch_result.get("message_ids", []))

        results["success"] = results["failed"] == 0

        logger.info(
            f"Batch send complete: {results['sent']} sent, {results['failed']} failed"
        )

        return results

    async def _send_single_batch(self, emails: list[dict]) -> dict[str, Any]:
        """Send a single batch of emails via SendGrid personalizations API."""
        if not emails:
            return {"sent": 0, "failed": 0, "errors": [], "message_ids": []}

        try:
            # Build personalizations array
            personalizations = []
            for email_data in emails:
                personalization = {
                    "to": [{"email": email_data["to_email"]}],
                    "subject": email_data["subject"],
                    "custom_args": {"tracking_id": str(email_data["tracking_id"])},
                }

                # Add recipient name if provided
                if email_data.get("to_name"):
                    personalization["to"][0]["name"] = email_data["to_name"]

                # Add merge fields as substitutions
                if email_data.get("merge_fields"):
                    personalization["substitutions"] = {
                        f"{{{{{k}}}}}": str(v)
                        for k, v in email_data["merge_fields"].items()
                    }

                personalizations.append(personalization)

            # Use first email's content as base (with substitution placeholders)
            first_email = emails[0]
            html_content = self._add_tracking(
                first_email["html_content"],
                "{{tracking_id}}"  # Placeholder, replaced by personalization
            )

            text_content = first_email.get("text_content") or self._html_to_text(
                first_email["html_content"]
            )

            # Build payload
            payload = {
                "personalizations": personalizations,
                "from": {
                    "email": self.from_email,
                    "name": self.from_name,
                },
                "content": [
                    {"type": "text/plain", "value": text_content},
                    {"type": "text/html", "value": html_content},
                ],
                "tracking_settings": {
                    "click_tracking": {"enable": True, "enable_text": False},
                    "open_tracking": {"enable": True},
                },
            }

            # Send via SendGrid API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/mail/send",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=60.0,  # Longer timeout for batch
                )

                if response.status_code in [200, 201, 202]:
                    message_id = response.headers.get("X-Message-Id", "batch")
                    logger.info(f"Batch sent successfully: {len(emails)} emails")
                    return {
                        "sent": len(emails),
                        "failed": 0,
                        "errors": [],
                        "message_ids": [message_id],
                    }
                else:
                    error_msg = f"SendGrid batch error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return {
                        "sent": 0,
                        "failed": len(emails),
                        "errors": [error_msg],
                        "message_ids": [],
                    }

        except Exception as e:
            error_msg = f"Batch send error: {str(e)}"
            logger.error(error_msg)
            return {
                "sent": 0,
                "failed": len(emails),
                "errors": [error_msg],
                "message_ids": [],
            }

    # =========================================================================
    # Tracking
    # =========================================================================

    def _add_tracking(self, html: str, tracking_id: str) -> str:
        """Add tracking pixel and unsubscribe link to HTML content."""
        # Add open tracking pixel (if custom tracking domain)
        if self.tracking_domain:
            pixel = f'<img src="{self.tracking_domain}/track/open/{tracking_id}" width="1" height="1" alt="" style="display:none;" />'
        else:
            # SendGrid handles open tracking automatically
            pixel = ""

        # Add unsubscribe link
        unsubscribe_link = self._get_unsubscribe_link(tracking_id)
        unsubscribe_html = f'''
        <p style="font-size: 11px; color: #666666; margin-top: 30px; text-align: center;">
            <a href="{unsubscribe_link}" style="color: #666666; text-decoration: underline;">Unsubscribe</a>
        </p>
        '''

        # Insert tracking before closing body tag
        if "</body>" in html.lower():
            html = re.sub(
                r"</body>",
                f"{pixel}{unsubscribe_html}</body>",
                html,
                flags=re.IGNORECASE
            )
        else:
            html = html + pixel + unsubscribe_html

        return html

    def _get_unsubscribe_link(self, tracking_id: str) -> str:
        """Generate unsubscribe link."""
        if self.tracking_domain:
            return f"{self.tracking_domain}/unsubscribe/{tracking_id}"
        else:
            # Use SendGrid's built-in unsubscribe
            return "<%asm_group_unsubscribe_raw_url%>"

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text."""
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", html)
        # Convert HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # =========================================================================
    # Webhook Processing
    # =========================================================================

    async def process_webhook(self, events: list[dict]) -> dict[str, int]:
        """
        Process SendGrid webhook events.

        Event types:
        - delivered: Email was delivered
        - open: Email was opened
        - click: Link was clicked
        - bounce: Email bounced
        - dropped: Email was dropped
        - spam_report: Marked as spam
        - unsubscribe: User unsubscribed

        Args:
            events: List of SendGrid event dictionaries

        Returns:
            Dict with counts by event type
        """
        counts = {}

        for event in events:
            event_type = event.get("event", "unknown")
            counts[event_type] = counts.get(event_type, 0) + 1

            tracking_id = (
                event.get("tracking_id") or
                event.get("sg_message_id") or
                event.get("custom_args", {}).get("tracking_id")
            )

            if tracking_id:
                logger.info(f"Email event: {event_type} for tracking_id={tracking_id}")

                # Handle specific events
                if event_type == "bounce":
                    await self._handle_bounce(tracking_id, event)
                elif event_type == "unsubscribe":
                    await self._handle_unsubscribe(tracking_id, event)
                elif event_type == "spam_report":
                    await self._handle_spam_report(tracking_id, event)

        return counts

    async def _handle_bounce(self, tracking_id: str, event: dict):
        """Handle bounce event."""
        bounce_type = event.get("type", "unknown")  # hard, soft
        reason = event.get("reason", "")
        logger.warning(f"Email bounce ({bounce_type}): {tracking_id} - {reason}")
        # Database update should be handled by calling code

    async def _handle_unsubscribe(self, tracking_id: str, event: dict):
        """Handle unsubscribe event."""
        logger.info(f"Email unsubscribe: {tracking_id}")
        # Database update should be handled by calling code

    async def _handle_spam_report(self, tracking_id: str, event: dict):
        """Handle spam report event."""
        logger.warning(f"Spam report: {tracking_id}")
        # Database update should be handled by calling code

    # =========================================================================
    # Validation
    # =========================================================================

    async def validate_email(self, email: str) -> dict[str, Any]:
        """
        Validate email address (uses SendGrid Email Validation if available).

        Args:
            email: Email address to validate

        Returns:
            Validation result dict
        """
        # Basic format validation
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, email):
            return {
                "valid": False,
                "reason": "Invalid email format",
            }

        # Check for common typos in domain
        common_domains = {
            "gmial.com": "gmail.com",
            "gmal.com": "gmail.com",
            "gamil.com": "gmail.com",
            "outloo.com": "outlook.com",
            "hotmal.com": "hotmail.com",
            "yahooo.com": "yahoo.com",
        }

        domain = email.split("@")[1].lower()
        if domain in common_domains:
            return {
                "valid": False,
                "reason": f"Possible typo. Did you mean @{common_domains[domain]}?",
                "suggestion": email.replace(domain, common_domains[domain]),
            }

        return {"valid": True}

    # =========================================================================
    # Email Templates
    # =========================================================================

    def create_html_email(
        self,
        body: str,
        preheader: str = "",
        signature: str | None = None,
    ) -> str:
        """
        Create a professional HTML email from body text.

        Args:
            body: Email body content (can include HTML)
            preheader: Preview text shown in inbox
            signature: Custom signature (optional)

        Returns:
            Full HTML email
        """
        default_signature = """
        <p style="color: #666666;">
            Best regards,<br>
            <strong>AI Whisperers Team</strong><br>
            <a href="https://ai-whisperers.com" style="color: #0066cc;">ai-whisperers.com</a>
        </p>
        """

        sig = signature or default_signature

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email</title>
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333333;">
    <!-- Preheader text (hidden) -->
    <div style="display: none; max-height: 0; overflow: hidden;">
        {preheader}
    </div>

    <!-- Email container -->
    <table role="presentation" style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 20px;">
                <table role="presentation" style="max-width: 600px; margin: 0 auto; background: #ffffff;">
                    <tr>
                        <td style="padding: 30px;">
                            <!-- Body content -->
                            {body}

                            <!-- Signature -->
                            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eeeeee;">
                                {sig}
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
        return html


# =============================================================================
# Factory Function
# =============================================================================


def get_email_service() -> EmailService:
    """Factory function to get EmailService instance."""
    return EmailService()


# =============================================================================
# Mock Service for Testing
# =============================================================================


class MockEmailService:
    """
    Mock email service for testing without SendGrid.
    """

    def __init__(self):
        self.sent_emails: list[dict] = []

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        tracking_id: str,
        **kwargs,
    ) -> EmailResult:
        """Mock send email."""
        self.sent_emails.append({
            "to_email": to_email,
            "subject": subject,
            "tracking_id": tracking_id,
            "timestamp": datetime.utcnow(),
        })

        logger.info(f"[MOCK] Email sent to {to_email}: {subject}")

        return EmailResult(
            success=True,
            message_id=f"mock_{tracking_id}",
            timestamp=datetime.utcnow()
        )

    async def send_batch(self, emails: list[dict]) -> list[EmailResult]:
        """Mock batch send."""
        results = []
        for email_data in emails:
            result = await self.send_email(**email_data)
            results.append(result)
        return results

    async def process_webhook(self, events: list[dict]) -> dict[str, int]:
        """Mock webhook processing."""
        return {"processed": len(events)}

    def create_html_email(self, body: str, preheader: str = "", signature: str = None) -> str:
        """Mock HTML email creation."""
        return f"<html><body>{body}</body></html>"
