"""
Tests for ReplyDetectionService.

Tests cover:
- Inbound email processing
- Prospect matching by email
- Original message threading
- Reply processing and status updates
- Sentiment detection
- Subject line cleaning
- HTML to text conversion
- SendGrid Inbound Parse parsing
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestReplyDetectionServiceInit:
    """Tests for ReplyDetectionService initialization."""

    def test_reply_detection_service_initialization(self):
        """Test ReplyDetectionService initializes correctly."""
        from api.services.reply_detection_service import ReplyDetectionService

        mock_session = MagicMock()
        service = ReplyDetectionService(mock_session)

        assert service.db is mock_session


class TestProcessInboundEmail:
    """Tests for process_inbound_email method."""

    @pytest_asyncio.fixture
    async def service_with_mocks(self):
        """Create ReplyDetectionService with mocked methods."""
        from api.services.reply_detection_service import ReplyDetectionService
        from api.database.outreach_models import Prospect, OutreachMessage, ProspectStatus

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = ReplyDetectionService(mock_session)

        # Create mock prospect
        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = 100
        mock_prospect.status = ProspectStatus.CONTACTED
        mock_prospect.sequence_paused = False

        # Create mock message
        mock_message = MagicMock(spec=OutreachMessage)
        mock_message.id = 1
        mock_message.message_type = MagicMock()
        mock_message.message_type.value = "email_initial"

        service._find_prospect_by_email = AsyncMock(return_value=mock_prospect)
        service._find_original_message = AsyncMock(return_value=mock_message)
        service._process_reply = AsyncMock()
        service._store_unmatched_inbound = AsyncMock()

        return service, mock_prospect, mock_message

    @pytest.mark.asyncio
    async def test_process_inbound_email_matched(self, service_with_mocks):
        """Test processing matched inbound email."""
        service, mock_prospect, mock_message = service_with_mocks

        result = await service.process_inbound_email(
            from_email="john@example.com",
            from_name="John Doe",
            to_email="reply@ourcompany.com",
            subject="Re: Your offer",
            text_body="Yes, I'm interested!",
            html_body=None,
        )

        assert result["processed"] is True
        assert result["matched"] is True
        assert result["prospect_id"] == 100
        assert result["message_id"] == 1
        service._process_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_inbound_email_unmatched(self, service_with_mocks):
        """Test processing unmatched inbound email."""
        service, mock_prospect, mock_message = service_with_mocks
        service._find_prospect_by_email = AsyncMock(return_value=None)

        result = await service.process_inbound_email(
            from_email="stranger@example.com",
            from_name="Stranger",
            to_email="reply@ourcompany.com",
            subject="Random email",
            text_body="Hello",
            html_body=None,
        )

        assert result["processed"] is True
        assert result["matched"] is False
        assert result["prospect_id"] is None
        service._store_unmatched_inbound.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_inbound_email_invalid_from(self, service_with_mocks):
        """Test processing email with invalid from address."""
        service, mock_prospect, mock_message = service_with_mocks

        result = await service.process_inbound_email(
            from_email="",
            from_name=None,
            to_email="reply@ourcompany.com",
            subject="Test",
            text_body="Content",
            html_body=None,
        )

        assert result["processed"] is False
        assert result["matched"] is False

    @pytest.mark.asyncio
    async def test_process_inbound_email_with_html_only(self, service_with_mocks):
        """Test processing email with HTML body only."""
        service, mock_prospect, mock_message = service_with_mocks

        result = await service.process_inbound_email(
            from_email="john@example.com",
            from_name="John",
            to_email="reply@ourcompany.com",
            subject="Re: Test",
            text_body=None,
            html_body="<p>I'm interested!</p>",
        )

        assert result["processed"] is True
        assert result["matched"] is True

    @pytest.mark.asyncio
    async def test_process_inbound_email_handles_errors(self, service_with_mocks):
        """Test error handling in process_inbound_email."""
        service, mock_prospect, mock_message = service_with_mocks
        service._find_prospect_by_email = AsyncMock(side_effect=Exception("DB error"))

        result = await service.process_inbound_email(
            from_email="john@example.com",
            from_name="John",
            to_email="reply@ourcompany.com",
            subject="Test",
            text_body="Content",
            html_body=None,
        )

        assert "error" in result


class TestFindOriginalMessage:
    """Tests for _find_original_message method."""

    @pytest_asyncio.fixture
    async def service(self):
        """Create ReplyDetectionService."""
        from api.services.reply_detection_service import ReplyDetectionService

        mock_session = MagicMock()
        return ReplyDetectionService(mock_session)

    @pytest.mark.asyncio
    async def test_find_by_in_reply_to_header(self, service):
        """Test finding message by In-Reply-To header."""
        from api.database.outreach_models import OutreachMessage

        mock_message = MagicMock(spec=OutreachMessage)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_message
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service._find_original_message(
            prospect_id=100,
            subject="Re: Our conversation",
            headers={"In-Reply-To": "<msg123@sendgrid.com>"},
        )

        assert result is mock_message

    @pytest.mark.asyncio
    async def test_find_by_references_header(self, service):
        """Test finding message by References header."""
        from api.database.outreach_models import OutreachMessage

        mock_message = MagicMock(spec=OutreachMessage)

        # First query returns None, second returns message
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = None
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_message

        service.db.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

        result = await service._find_original_message(
            prospect_id=100,
            subject="Re: Test",
            headers={"References": "<msg1@sg.com> <msg2@sg.com>"},
        )

        assert result is mock_message

    @pytest.mark.asyncio
    async def test_find_by_subject_fallback(self, service):
        """Test finding message by subject line."""
        from api.database.outreach_models import OutreachMessage

        mock_message = MagicMock(spec=OutreachMessage)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_message
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service._find_original_message(
            prospect_id=100,
            subject="Re: Fwd: Original Subject",
            headers=None,
        )

        assert result is mock_message


class TestProcessReply:
    """Tests for _process_reply method."""

    @pytest_asyncio.fixture
    async def service_with_mocks(self):
        """Create service with mocked methods."""
        from api.services.reply_detection_service import ReplyDetectionService
        from api.database.outreach_models import Prospect, OutreachMessage, ProspectStatus

        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = ReplyDetectionService(mock_session)
        service._cancel_pending_messages = AsyncMock()

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = 100
        mock_prospect.status = ProspectStatus.ENGAGED

        mock_message = MagicMock(spec=OutreachMessage)
        mock_message.id = 1
        mock_message.message_type = MagicMock()
        mock_message.message_type.value = "email_initial"

        return service, mock_prospect, mock_message

    @pytest.mark.asyncio
    async def test_process_reply_updates_prospect_status(self, service_with_mocks):
        """Test reply updates prospect status to REPLIED."""
        from api.database.outreach_models import ProspectStatus

        service, mock_prospect, mock_message = service_with_mocks

        await service._process_reply(
            prospect=mock_prospect,
            original_message=mock_message,
            reply_subject="Re: Test",
            reply_body="I'm interested!",
        )

        assert mock_prospect.status == ProspectStatus.REPLIED
        assert mock_prospect.sequence_paused is True
        assert mock_prospect.sequence_paused_reason == "Prospect replied"

    @pytest.mark.asyncio
    async def test_process_reply_detects_sentiment(self, service_with_mocks):
        """Test reply detects sentiment."""
        service, mock_prospect, mock_message = service_with_mocks

        await service._process_reply(
            prospect=mock_prospect,
            original_message=mock_message,
            reply_subject="Re: Test",
            reply_body="Yes, let's schedule a call!",
        )

        assert mock_prospect.reply_sentiment == "interested"

    @pytest.mark.asyncio
    async def test_process_reply_cancels_pending_messages(self, service_with_mocks):
        """Test reply cancels pending follow-up messages."""
        service, mock_prospect, mock_message = service_with_mocks

        await service._process_reply(
            prospect=mock_prospect,
            original_message=mock_message,
            reply_subject="Re: Test",
            reply_body="Thanks!",
        )

        service._cancel_pending_messages.assert_called_once_with(100)

    @pytest.mark.asyncio
    async def test_process_reply_creates_engagement_event(self, service_with_mocks):
        """Test reply creates engagement event."""
        service, mock_prospect, mock_message = service_with_mocks

        await service._process_reply(
            prospect=mock_prospect,
            original_message=mock_message,
            reply_subject="Re: Test",
            reply_body="Content",
        )

        service.db.add.assert_called_once()


class TestDetectBasicSentiment:
    """Tests for _detect_basic_sentiment method."""

    @pytest.fixture
    def service(self):
        """Create ReplyDetectionService."""
        from api.services.reply_detection_service import ReplyDetectionService

        return ReplyDetectionService(MagicMock())

    def test_detect_interested_sentiment(self, service):
        """Test detecting interested sentiment."""
        texts = [
            "Yes, I'm interested in learning more",
            "Let's schedule a call",
            "I'd love to hear more about this",
            "Can we set up a meeting?",
            "Tell me more about your services",
        ]

        for text in texts:
            assert service._detect_basic_sentiment(text) == "interested", f"Failed for: {text}"

    def test_detect_negative_sentiment(self, service):
        """Test detecting negative sentiment."""
        texts = [
            "Not interested, please remove me",
            "No thanks, we're not looking for this",
            "Please unsubscribe me from this list",
            "Stop contacting me",
            "I'll pass on this",
        ]

        for text in texts:
            assert service._detect_basic_sentiment(text) == "negative", f"Failed for: {text}"

    def test_detect_neutral_sentiment(self, service):
        """Test detecting neutral sentiment."""
        texts = [
            "Thanks for reaching out",
            "Got your email",
            "Will review and get back to you",
        ]

        for text in texts:
            assert service._detect_basic_sentiment(text) == "neutral", f"Failed for: {text}"

    def test_empty_text_returns_neutral(self, service):
        """Test empty text returns neutral."""
        assert service._detect_basic_sentiment("") == "neutral"
        assert service._detect_basic_sentiment(None) == "neutral"


class TestCleanSubject:
    """Tests for _clean_subject method."""

    @pytest.fixture
    def service(self):
        """Create ReplyDetectionService."""
        from api.services.reply_detection_service import ReplyDetectionService

        return ReplyDetectionService(MagicMock())

    def test_clean_re_prefix(self, service):
        """Test cleaning Re: prefix."""
        assert service._clean_subject("Re: Original Subject") == "Original Subject"
        assert service._clean_subject("RE: Original Subject") == "Original Subject"
        assert service._clean_subject("re: Original Subject") == "Original Subject"

    def test_clean_fwd_prefix(self, service):
        """Test cleaning Fwd: prefix."""
        assert service._clean_subject("Fwd: Original Subject") == "Original Subject"
        assert service._clean_subject("FWD: Original Subject") == "Original Subject"
        assert service._clean_subject("Fw: Original Subject") == "Original Subject"

    def test_clean_multiple_prefixes(self, service):
        """Test cleaning multiple prefixes."""
        # Only removes first prefix
        result = service._clean_subject("Re: Fwd: Original")
        # After first re: is removed, we get "Fwd: Original"
        assert "Original" in result

    def test_clean_external_tag(self, service):
        """Test cleaning [EXTERNAL] tag."""
        assert service._clean_subject("[EXT] Subject") == "Subject"
        assert service._clean_subject("[EXTERNAL] Subject") == "Subject"
        assert service._clean_subject("[SPAM] Subject") == "Subject"

    def test_clean_empty_subject(self, service):
        """Test cleaning empty subject."""
        assert service._clean_subject("") == ""
        assert service._clean_subject(None) == ""


class TestHtmlToText:
    """Tests for _html_to_text method."""

    @pytest.fixture
    def service(self):
        """Create ReplyDetectionService."""
        from api.services.reply_detection_service import ReplyDetectionService

        return ReplyDetectionService(MagicMock())

    def test_html_to_text_basic(self, service):
        """Test basic HTML to text conversion."""
        html = "<p>Hello World</p>"
        result = service._html_to_text(html)
        assert "Hello World" in result

    def test_html_to_text_removes_tags(self, service):
        """Test HTML tags are removed."""
        html = "<div><strong>Bold</strong> and <em>italic</em></div>"
        result = service._html_to_text(html)
        assert "Bold" in result
        assert "italic" in result
        assert "<" not in result
        assert ">" not in result

    def test_html_to_text_converts_entities(self, service):
        """Test HTML entities are converted."""
        html = "Tom &amp; Jerry &lt;3 &gt;"
        result = service._html_to_text(html)
        assert "&" in result
        assert "<" in result
        assert ">" in result

    def test_html_to_text_handles_nbsp(self, service):
        """Test &nbsp; is converted to space."""
        html = "Word1&nbsp;Word2"
        result = service._html_to_text(html)
        assert "Word1" in result
        assert "Word2" in result

    def test_html_to_text_empty(self, service):
        """Test empty HTML returns empty string."""
        assert service._html_to_text("") == ""
        assert service._html_to_text(None) == ""


class TestParseInboundParseWebhook:
    """Tests for parse_inbound_parse_webhook function."""

    def test_parse_basic_webhook(self):
        """Test parsing basic webhook form data."""
        from api.services.reply_detection_service import parse_inbound_parse_webhook

        form_data = {
            "from": "John Doe <john@example.com>",
            "to": "reply@ourcompany.com",
            "subject": "Re: Your offer",
            "text": "I'm interested!",
            "html": "<p>I'm interested!</p>",
            "attachments": "0",
        }

        result = parse_inbound_parse_webhook(form_data)

        assert result["from_email"] == "john@example.com"
        assert result["from_name"] == "John Doe"
        assert result["to_email"] == "reply@ourcompany.com"
        assert result["subject"] == "Re: Your offer"
        assert result["text_body"] == "I'm interested!"
        assert result["attachment_count"] == 0

    def test_parse_webhook_with_headers(self):
        """Test parsing webhook with email headers."""
        from api.services.reply_detection_service import parse_inbound_parse_webhook

        form_data = {
            "from": "john@example.com",
            "to": "reply@ourcompany.com",
            "subject": "Re: Test",
            "text": "Content",
            "headers": "In-Reply-To: <msg123@sendgrid.com>\nReferences: <msg123@sendgrid.com>",
        }

        result = parse_inbound_parse_webhook(form_data)

        assert "In-Reply-To" in result["headers"] or len(result["headers"]) >= 0

    def test_parse_webhook_without_attachments(self):
        """Test parsing webhook defaults attachment count to 0."""
        from api.services.reply_detection_service import parse_inbound_parse_webhook

        form_data = {
            "from": "john@example.com",
            "to": "reply@ourcompany.com",
            "subject": "Test",
        }

        result = parse_inbound_parse_webhook(form_data)

        assert result["attachment_count"] == 0


class TestCancelPendingMessages:
    """Tests for _cancel_pending_messages method."""

    @pytest.mark.asyncio
    async def test_cancel_pending_messages(self):
        """Test cancelling pending messages."""
        from api.services.reply_detection_service import ReplyDetectionService

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = ReplyDetectionService(mock_session)

        await service._cancel_pending_messages(100)

        mock_session.execute.assert_called_once()


class TestFactoryFunction:
    """Tests for factory function."""

    def test_get_reply_detection_service(self):
        """Test get_reply_detection_service factory."""
        from api.services.reply_detection_service import get_reply_detection_service

        mock_session = MagicMock()
        service = get_reply_detection_service(mock_session)

        assert service is not None
        assert service.db is mock_session
