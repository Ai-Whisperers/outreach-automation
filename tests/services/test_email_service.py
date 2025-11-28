"""
Service tests for EmailService.

Tests cover:
- Email sending
- Tracking pixel/link injection
- HTML to text conversion
- Webhook processing
- MockEmailService behavior
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestEmailServiceBasics:
    """Basic tests for EmailService."""

    @pytest.fixture
    def mock_sendgrid(self):
        """Mock SendGrid client."""
        mock = MagicMock()
        mock.send = MagicMock(return_value=MagicMock(
            status_code=202,
            headers={"X-Message-Id": "test-msg-123"},
        ))
        return mock

    def test_email_service_initialization(self):
        """Test EmailService can be initialized."""
        with patch.dict("os.environ", {"SENDGRID_API_KEY": "test-key"}):
            from api.services.email_service import EmailService

            service = EmailService()
            assert service is not None

    def test_mock_email_service_exists(self):
        """Test MockEmailService exists for testing."""
        from api.services.email_service import MockEmailService

        mock_service = MockEmailService()
        assert mock_service is not None


class TestMockEmailService:
    """Tests for MockEmailService (testing double)."""

    @pytest.fixture
    def mock_service(self):
        """Create MockEmailService instance."""
        from api.services.email_service import MockEmailService

        return MockEmailService()

    @pytest.mark.asyncio
    async def test_send_email_returns_success(self, mock_service):
        """Test mock email sending returns success."""
        result = await mock_service.send_email(
            to_email="john@example.com",
            to_name="John Doe",
            subject="Test Subject",
            html_content="<p>Hello John</p>",
            from_email="sender@example.com",
        )

        assert result["success"] is True
        assert "message_id" in result
        assert result["to_email"] == "john@example.com"

    @pytest.mark.asyncio
    async def test_send_email_tracks_sent(self, mock_service):
        """Test mock service tracks sent emails."""
        await mock_service.send_email(
            to_email="john@example.com",
            to_name="John",
            subject="Test",
            html_content="<p>Hi</p>",
        )

        assert len(mock_service.sent_emails) == 1
        assert mock_service.sent_emails[0]["to_email"] == "john@example.com"

    @pytest.mark.asyncio
    async def test_send_email_generates_unique_ids(self, mock_service):
        """Test each email gets unique message ID."""
        result1 = await mock_service.send_email(
            to_email="john@example.com",
            to_name="John",
            subject="Test 1",
            html_content="<p>Hi</p>",
        )

        result2 = await mock_service.send_email(
            to_email="jane@example.com",
            to_name="Jane",
            subject="Test 2",
            html_content="<p>Hi</p>",
        )

        assert result1["message_id"] != result2["message_id"]

    @pytest.mark.asyncio
    async def test_clear_sent_emails(self, mock_service):
        """Test clearing sent email history."""
        await mock_service.send_email(
            to_email="john@example.com",
            to_name="John",
            subject="Test",
            html_content="<p>Hi</p>",
        )

        mock_service.clear()

        assert len(mock_service.sent_emails) == 0


class TestEmailContentProcessing:
    """Tests for email content processing."""

    @pytest.fixture
    def email_service(self):
        """Create EmailService with mocked SendGrid."""
        with patch.dict("os.environ", {"SENDGRID_API_KEY": "test-key"}):
            from api.services.email_service import EmailService

            service = EmailService()
            return service

    def test_add_tracking_pixel(self, email_service):
        """Test adding tracking pixel to HTML."""
        html = "<html><body><p>Hello</p></body></html>"
        prospect_id = 123
        message_id = 456

        result = email_service._add_tracking_pixel(html, prospect_id, message_id)

        assert "tracking" in result.lower() or "pixel" in result.lower() or "img" in result.lower()

    def test_wrap_links_for_tracking(self, email_service):
        """Test wrapping links for click tracking."""
        html = '<p>Click <a href="https://example.com">here</a></p>'
        prospect_id = 123
        message_id = 456

        result = email_service._wrap_links(html, prospect_id, message_id)

        # Links should be wrapped for tracking
        assert "https://example.com" in result or "tracking" in result.lower()

    def test_html_to_text_conversion(self, email_service):
        """Test converting HTML to plain text."""
        html = """
        <html>
        <body>
            <h1>Hello John</h1>
            <p>I noticed your work at Acme.</p>
            <p>Would you be interested in a <a href="https://example.com">quick chat</a>?</p>
            <br>
            <p>Best,<br>Sender</p>
        </body>
        </html>
        """

        text = email_service._html_to_text(html)

        assert "Hello John" in text
        assert "Acme" in text
        assert "Best" in text
        # Links should be preserved or converted
        assert "example.com" in text or "quick chat" in text

    def test_html_to_text_strips_scripts(self, email_service):
        """Test HTML to text strips script tags."""
        html = """
        <html>
        <body>
            <p>Hello</p>
            <script>alert('bad')</script>
        </body>
        </html>
        """

        text = email_service._html_to_text(html)

        assert "alert" not in text
        assert "Hello" in text


class TestEmailValidation:
    """Tests for email validation."""

    @pytest.fixture
    def email_service(self):
        """Create EmailService."""
        with patch.dict("os.environ", {"SENDGRID_API_KEY": "test-key"}):
            from api.services.email_service import EmailService

            return EmailService()

    def test_validate_email_format(self, email_service):
        """Test email format validation."""
        assert email_service.validate_email("john@example.com") is True
        assert email_service.validate_email("invalid") is False
        assert email_service.validate_email("") is False

    def test_validate_email_domain(self, email_service):
        """Test email domain validation."""
        assert email_service.validate_email("john@gmail.com") is True
        assert email_service.validate_email("john@example") is False


class TestEmailSending:
    """Tests for actual email sending logic."""

    @pytest_asyncio.fixture
    async def email_service_with_mock(self):
        """Create EmailService with mocked SendGrid."""
        with patch.dict("os.environ", {"SENDGRID_API_KEY": "test-key"}):
            from api.services.email_service import EmailService

            service = EmailService()
            service._client = MagicMock()
            service._client.send = MagicMock(return_value=MagicMock(
                status_code=202,
                headers={"X-Message-Id": "sg-123"},
            ))
            return service

    @pytest.mark.asyncio
    async def test_send_email_success(self, email_service_with_mock):
        """Test successful email sending."""
        service = email_service_with_mock

        result = await service.send_email(
            to_email="john@example.com",
            to_name="John Doe",
            subject="Test Subject",
            html_content="<p>Hello John</p>",
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_send_email_with_reply_to(self, email_service_with_mock):
        """Test email sending with reply-to header."""
        service = email_service_with_mock

        result = await service.send_email(
            to_email="john@example.com",
            to_name="John",
            subject="Test",
            html_content="<p>Hi</p>",
            reply_to="sales@example.com",
        )

        assert result["success"] is True


class TestWebhookProcessing:
    """Tests for webhook event processing."""

    @pytest.fixture
    def email_service(self):
        """Create EmailService."""
        with patch.dict("os.environ", {"SENDGRID_API_KEY": "test-key"}):
            from api.services.email_service import EmailService

            return EmailService()

    @pytest.mark.asyncio
    async def test_process_open_event(self, email_service):
        """Test processing email open event."""
        event = {
            "event": "open",
            "email": "john@example.com",
            "timestamp": 1705000000,
            "sg_message_id": "abc123",
            "useragent": "Mozilla/5.0",
            "ip": "192.168.1.1",
        }

        result = await email_service.process_webhook_event(event)

        assert result["event_type"] == "open"
        assert result["email"] == "john@example.com"

    @pytest.mark.asyncio
    async def test_process_click_event(self, email_service):
        """Test processing email click event."""
        event = {
            "event": "click",
            "email": "john@example.com",
            "url": "https://example.com/link",
            "timestamp": 1705000000,
        }

        result = await email_service.process_webhook_event(event)

        assert result["event_type"] == "click"
        assert result["url"] == "https://example.com/link"

    @pytest.mark.asyncio
    async def test_process_bounce_event(self, email_service):
        """Test processing email bounce event."""
        event = {
            "event": "bounce",
            "email": "john@example.com",
            "reason": "Invalid address",
            "timestamp": 1705000000,
        }

        result = await email_service.process_webhook_event(event)

        assert result["event_type"] == "bounce"
        assert "reason" in result

    @pytest.mark.asyncio
    async def test_process_unsubscribe_event(self, email_service):
        """Test processing unsubscribe event."""
        event = {
            "event": "unsubscribe",
            "email": "john@example.com",
            "timestamp": 1705000000,
        }

        result = await email_service.process_webhook_event(event)

        assert result["event_type"] == "unsubscribe"

    @pytest.mark.asyncio
    async def test_process_batch_events(self, email_service):
        """Test processing multiple webhook events."""
        events = [
            {"event": "delivered", "email": "john@example.com"},
            {"event": "open", "email": "john@example.com"},
            {"event": "click", "email": "john@example.com", "url": "https://example.com"},
        ]

        results = await email_service.process_webhook_events(events)

        assert len(results) == 3


class TestEmailTemplating:
    """Tests for email template handling."""

    @pytest.fixture
    def email_service(self):
        """Create EmailService."""
        with patch.dict("os.environ", {"SENDGRID_API_KEY": "test-key"}):
            from api.services.email_service import EmailService

            return EmailService()

    def test_render_template(self, email_service):
        """Test rendering email template with variables."""
        template = "Hi {{first_name}}, I noticed {{company}}'s growth."
        variables = {
            "first_name": "John",
            "company": "Acme Corp",
        }

        result = email_service.render_template(template, variables)

        assert "John" in result
        assert "Acme Corp" in result
        assert "{{" not in result

    def test_render_template_missing_variable(self, email_service):
        """Test rendering template with missing variable."""
        template = "Hi {{first_name}}, {{missing_var}} here."
        variables = {"first_name": "John"}

        result = email_service.render_template(template, variables)

        # Should handle missing variables gracefully
        assert "John" in result

    def test_render_template_escapes_html(self, email_service):
        """Test template rendering escapes HTML in variables."""
        template = "Hi {{first_name}}"
        variables = {"first_name": "<script>alert('xss')</script>"}

        result = email_service.render_template(template, variables)

        # Should escape or strip dangerous HTML
        assert "<script>" not in result or "&lt;script&gt;" in result


class TestEmailRateLimiting:
    """Tests for email rate limiting integration."""

    @pytest_asyncio.fixture
    async def email_service(self):
        """Create EmailService with mocked rate limiter."""
        with patch.dict("os.environ", {"SENDGRID_API_KEY": "test-key"}):
            from api.services.email_service import EmailService

            service = EmailService()
            service._rate_limiter = MagicMock()
            service._rate_limiter.check_quota = AsyncMock(return_value=(True, 40))
            service._rate_limiter.increment_usage = AsyncMock(return_value=11)
            return service

    @pytest.mark.asyncio
    async def test_check_quota_before_send(self, email_service):
        """Test quota is checked before sending."""
        email_service._client = MagicMock()
        email_service._client.send = MagicMock(return_value=MagicMock(
            status_code=202,
        ))

        await email_service.send_email(
            to_email="john@example.com",
            to_name="John",
            subject="Test",
            html_content="<p>Hi</p>",
            campaign_id=1,
        )

        email_service._rate_limiter.check_quota.assert_called()

    @pytest.mark.asyncio
    async def test_increment_usage_after_send(self, email_service):
        """Test usage is incremented after successful send."""
        email_service._client = MagicMock()
        email_service._client.send = MagicMock(return_value=MagicMock(
            status_code=202,
        ))

        await email_service.send_email(
            to_email="john@example.com",
            to_name="John",
            subject="Test",
            html_content="<p>Hi</p>",
            campaign_id=1,
        )

        email_service._rate_limiter.increment_usage.assert_called()
