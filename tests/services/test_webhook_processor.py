"""
Tests for WebhookProcessor service.

Tests cover:
- SendGrid webhook event processing
- Event handlers (delivered, open, click, bounce, spam, unsubscribe)
- Tracking ID extraction
- Message/prospect status updates
- Engagement event creation
- Pending message cancellation
- Signature verification
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestWebhookProcessorInit:
    """Tests for WebhookProcessor initialization."""

    def test_webhook_processor_initialization(self):
        """Test WebhookProcessor initializes correctly."""
        from api.services.webhook_processor import WebhookProcessor

        mock_session = MagicMock()
        processor = WebhookProcessor(mock_session)

        assert processor.db is mock_session


class TestExtractTrackingId:
    """Tests for tracking ID extraction."""

    @pytest.fixture
    def processor(self):
        """Create WebhookProcessor with mock session."""
        from api.services.webhook_processor import WebhookProcessor

        return WebhookProcessor(MagicMock())

    def test_extract_from_custom_args(self, processor):
        """Test extracting tracking ID from custom_args."""
        event = {
            "event": "open",
            "custom_args": {"tracking_id": "12345"},
        }

        result = processor._extract_tracking_id(event)

        assert result == "12345"

    def test_extract_from_sg_message_id(self, processor):
        """Test extracting tracking ID from sg_message_id."""
        event = {
            "event": "open",
            "sg_message_id": "abc123.filter.subaccount",
        }

        result = processor._extract_tracking_id(event)

        assert result == "abc123"

    def test_extract_from_tracking_id_field(self, processor):
        """Test extracting tracking ID from tracking_id field."""
        event = {
            "event": "open",
            "tracking_id": "98765",
        }

        result = processor._extract_tracking_id(event)

        assert result == "98765"

    def test_extract_from_message_id_field(self, processor):
        """Test extracting tracking ID from message_id field."""
        event = {
            "event": "open",
            "message_id": "msg-001",
        }

        result = processor._extract_tracking_id(event)

        assert result == "msg-001"

    def test_extract_returns_none_when_missing(self, processor):
        """Test returns None when no tracking ID found."""
        event = {"event": "open"}

        result = processor._extract_tracking_id(event)

        assert result is None


class TestProcessSendGridEvents:
    """Tests for process_sendgrid_events method."""

    @pytest_asyncio.fixture
    async def processor_with_mocks(self):
        """Create WebhookProcessor with mocked database."""
        from api.services.webhook_processor import WebhookProcessor

        mock_session = MagicMock()
        mock_session.commit = AsyncMock()

        processor = WebhookProcessor(mock_session)

        # Mock helper methods
        processor._get_message = AsyncMock(return_value=None)
        processor._get_prospect = AsyncMock(return_value=None)

        return processor

    @pytest.mark.asyncio
    async def test_process_empty_events(self, processor_with_mocks):
        """Test processing empty event list."""
        result = await processor_with_mocks.process_sendgrid_events([])

        assert result["processed"] == 0
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_process_multiple_events(self, processor_with_mocks):
        """Test processing multiple events."""
        events = [
            {"event": "delivered", "custom_args": {"tracking_id": "1"}},
            {"event": "open", "custom_args": {"tracking_id": "2"}},
            {"event": "click", "custom_args": {"tracking_id": "3"}},
        ]

        result = await processor_with_mocks.process_sendgrid_events(events)

        assert result["processed"] == 3

    @pytest.mark.asyncio
    async def test_process_events_with_errors(self, processor_with_mocks):
        """Test processing events handles errors gracefully."""
        processor_with_mocks._handle_delivered = AsyncMock(side_effect=Exception("DB error"))

        events = [
            {"event": "delivered", "custom_args": {"tracking_id": "1"}},
        ]

        result = await processor_with_mocks.process_sendgrid_events(events)

        assert result["errors"] == 1

    @pytest.mark.asyncio
    async def test_process_events_skips_missing_tracking_id(self, processor_with_mocks):
        """Test events without tracking ID are skipped."""
        events = [
            {"event": "open"},  # No tracking_id
        ]

        result = await processor_with_mocks.process_sendgrid_events(events)

        assert result["processed"] == 1
        assert result["open"] == 0


class TestHandleDelivered:
    """Tests for delivered event handler."""

    @pytest_asyncio.fixture
    async def processor_with_message(self):
        """Create processor with mocked message."""
        from api.services.webhook_processor import WebhookProcessor
        from api.database.outreach_models import OutreachMessage, MessageStatus

        mock_session = MagicMock()
        mock_session.add = MagicMock()

        processor = WebhookProcessor(mock_session)

        # Create mock message
        mock_message = MagicMock(spec=OutreachMessage)
        mock_message.id = 1
        mock_message.prospect_id = 100
        mock_message.status = MessageStatus.SCHEDULED

        processor._get_message = AsyncMock(return_value=mock_message)
        processor._create_engagement_event = AsyncMock()

        return processor, mock_message

    @pytest.mark.asyncio
    async def test_handle_delivered_updates_message(self, processor_with_message):
        """Test delivered event updates message status."""
        from api.database.outreach_models import MessageStatus

        processor, mock_message = processor_with_message

        event = {"sg_message_id": "sg-123", "sg_event_id": "evt-456"}
        await processor._handle_delivered("1", event)

        assert mock_message.status == MessageStatus.SENT
        assert mock_message.delivered_at is not None
        assert mock_message.external_message_id == "sg-123"

    @pytest.mark.asyncio
    async def test_handle_delivered_creates_engagement_event(self, processor_with_message):
        """Test delivered event creates engagement record."""
        processor, mock_message = processor_with_message

        event = {"sg_event_id": "evt-456"}
        await processor._handle_delivered("1", event)

        processor._create_engagement_event.assert_called_once()
        call_kwargs = processor._create_engagement_event.call_args[1]
        assert call_kwargs["event_type"] == "delivered"


class TestHandleOpen:
    """Tests for open event handler."""

    @pytest_asyncio.fixture
    async def processor_with_message_and_prospect(self):
        """Create processor with mocked message and prospect."""
        from api.services.webhook_processor import WebhookProcessor
        from api.database.outreach_models import OutreachMessage, Prospect, ProspectStatus

        mock_session = MagicMock()
        mock_session.add = MagicMock()

        processor = WebhookProcessor(mock_session)

        # Create mock message
        mock_message = MagicMock(spec=OutreachMessage)
        mock_message.id = 1
        mock_message.prospect_id = 100
        mock_message.opened_at = None
        mock_message.open_count = 0

        # Create mock prospect
        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = 100
        mock_prospect.status = ProspectStatus.CONTACTED
        mock_prospect.engagement_score = 0

        processor._get_message = AsyncMock(return_value=mock_message)
        processor._get_prospect = AsyncMock(return_value=mock_prospect)
        processor._create_engagement_event = AsyncMock()

        return processor, mock_message, mock_prospect

    @pytest.mark.asyncio
    async def test_handle_open_first_open(self, processor_with_message_and_prospect):
        """Test first open sets opened_at timestamp."""
        processor, mock_message, mock_prospect = processor_with_message_and_prospect

        event = {"ip": "1.2.3.4", "useragent": "Mozilla/5.0"}
        await processor._handle_open("1", event)

        assert mock_message.opened_at is not None
        assert mock_message.open_count == 1

    @pytest.mark.asyncio
    async def test_handle_open_increments_count(self, processor_with_message_and_prospect):
        """Test subsequent opens increment count."""
        processor, mock_message, mock_prospect = processor_with_message_and_prospect
        mock_message.opened_at = datetime.utcnow()
        mock_message.open_count = 2

        event = {}
        await processor._handle_open("1", event)

        assert mock_message.open_count == 3

    @pytest.mark.asyncio
    async def test_handle_open_updates_prospect_status(self, processor_with_message_and_prospect):
        """Test open updates prospect to engaged status."""
        from api.database.outreach_models import ProspectStatus

        processor, mock_message, mock_prospect = processor_with_message_and_prospect

        event = {}
        await processor._handle_open("1", event)

        assert mock_prospect.status == ProspectStatus.ENGAGED
        assert mock_prospect.engagement_score == 1


class TestHandleClick:
    """Tests for click event handler."""

    @pytest_asyncio.fixture
    async def processor_with_mocks(self):
        """Create processor with mocked message and prospect."""
        from api.services.webhook_processor import WebhookProcessor
        from api.database.outreach_models import OutreachMessage, Prospect, ProspectStatus

        mock_session = MagicMock()

        processor = WebhookProcessor(mock_session)

        mock_message = MagicMock(spec=OutreachMessage)
        mock_message.id = 1
        mock_message.prospect_id = 100
        mock_message.clicked_at = None
        mock_message.click_count = 0

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = 100
        mock_prospect.status = ProspectStatus.CONTACTED
        mock_prospect.engagement_score = 1

        processor._get_message = AsyncMock(return_value=mock_message)
        processor._get_prospect = AsyncMock(return_value=mock_prospect)
        processor._create_engagement_event = AsyncMock()

        return processor, mock_message, mock_prospect

    @pytest.mark.asyncio
    async def test_handle_click_first_click(self, processor_with_mocks):
        """Test first click sets clicked_at timestamp."""
        processor, mock_message, mock_prospect = processor_with_mocks

        event = {"url": "https://example.com/link"}
        await processor._handle_click("1", event)

        assert mock_message.clicked_at is not None
        assert mock_message.click_count == 1

    @pytest.mark.asyncio
    async def test_handle_click_increases_engagement_score(self, processor_with_mocks):
        """Test click increases engagement score by 2."""
        processor, mock_message, mock_prospect = processor_with_mocks

        event = {"url": "https://example.com"}
        await processor._handle_click("1", event)

        assert mock_prospect.engagement_score == 3  # 1 + 2


class TestHandleBounce:
    """Tests for bounce event handler."""

    @pytest_asyncio.fixture
    async def processor_with_mocks(self):
        """Create processor with mocked message and prospect."""
        from api.services.webhook_processor import WebhookProcessor
        from api.database.outreach_models import OutreachMessage, Prospect, ProspectStatus, MessageStatus

        mock_session = MagicMock()

        processor = WebhookProcessor(mock_session)

        mock_message = MagicMock(spec=OutreachMessage)
        mock_message.id = 1
        mock_message.prospect_id = 100
        mock_message.status = MessageStatus.SENT

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = 100
        mock_prospect.status = ProspectStatus.CONTACTED
        mock_prospect.sequence_paused = False

        processor._get_message = AsyncMock(return_value=mock_message)
        processor._get_prospect = AsyncMock(return_value=mock_prospect)
        processor._create_engagement_event = AsyncMock()
        processor._cancel_pending_messages = AsyncMock()

        return processor, mock_message, mock_prospect

    @pytest.mark.asyncio
    async def test_handle_hard_bounce(self, processor_with_mocks):
        """Test hard bounce marks prospect as bounced."""
        from api.database.outreach_models import ProspectStatus, MessageStatus

        processor, mock_message, mock_prospect = processor_with_mocks

        event = {"type": "hard", "reason": "Invalid email address"}
        await processor._handle_bounce("1", event)

        assert mock_message.status == MessageStatus.FAILED
        assert mock_message.bounce_type == "hard"
        assert mock_prospect.status == ProspectStatus.BOUNCED
        assert mock_prospect.email_status == "bounced"
        assert mock_prospect.sequence_paused is True

    @pytest.mark.asyncio
    async def test_handle_soft_bounce(self, processor_with_mocks):
        """Test soft bounce sets email_status but not prospect status."""
        from api.database.outreach_models import ProspectStatus, MessageStatus

        processor, mock_message, mock_prospect = processor_with_mocks

        event = {"type": "soft", "reason": "Mailbox full"}
        await processor._handle_bounce("1", event)

        assert mock_message.status == MessageStatus.FAILED
        assert mock_prospect.email_status == "soft_bounced"
        # Status should not change for soft bounce
        assert mock_prospect.status == ProspectStatus.CONTACTED

    @pytest.mark.asyncio
    async def test_handle_bounce_cancels_pending_messages(self, processor_with_mocks):
        """Test bounce cancels pending follow-up messages."""
        processor, mock_message, mock_prospect = processor_with_mocks

        event = {"type": "hard", "reason": "Invalid"}
        await processor._handle_bounce("1", event)

        processor._cancel_pending_messages.assert_called_once_with(100)


class TestHandleSpamReport:
    """Tests for spam report event handler."""

    @pytest_asyncio.fixture
    async def processor_with_mocks(self):
        """Create processor with mocked message and prospect."""
        from api.services.webhook_processor import WebhookProcessor
        from api.database.outreach_models import OutreachMessage, Prospect, ProspectStatus

        mock_session = MagicMock()

        processor = WebhookProcessor(mock_session)

        mock_message = MagicMock(spec=OutreachMessage)
        mock_message.id = 1
        mock_message.prospect_id = 100

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = 100
        mock_prospect.status = ProspectStatus.CONTACTED

        processor._get_message = AsyncMock(return_value=mock_message)
        processor._get_prospect = AsyncMock(return_value=mock_prospect)
        processor._create_engagement_event = AsyncMock()
        processor._cancel_pending_messages = AsyncMock()

        return processor, mock_message, mock_prospect

    @pytest.mark.asyncio
    async def test_handle_spam_report_opts_out_prospect(self, processor_with_mocks):
        """Test spam report opts out prospect immediately."""
        from api.database.outreach_models import ProspectStatus

        processor, mock_message, mock_prospect = processor_with_mocks

        event = {"sg_event_id": "evt-123"}
        await processor._handle_spam_report("1", event)

        assert mock_prospect.status == ProspectStatus.OPTED_OUT
        assert mock_prospect.email_status == "complained"
        assert mock_prospect.sequence_paused is True
        assert "Spam report" in mock_prospect.sequence_paused_reason

    @pytest.mark.asyncio
    async def test_handle_spam_report_cancels_all_messages(self, processor_with_mocks):
        """Test spam report cancels all pending messages."""
        processor, mock_message, mock_prospect = processor_with_mocks

        event = {}
        await processor._handle_spam_report("1", event)

        processor._cancel_pending_messages.assert_called_once()


class TestHandleUnsubscribe:
    """Tests for unsubscribe event handler."""

    @pytest_asyncio.fixture
    async def processor_with_mocks(self):
        """Create processor with mocked message and prospect."""
        from api.services.webhook_processor import WebhookProcessor
        from api.database.outreach_models import OutreachMessage, Prospect, ProspectStatus

        mock_session = MagicMock()

        processor = WebhookProcessor(mock_session)

        mock_message = MagicMock(spec=OutreachMessage)
        mock_message.id = 1
        mock_message.prospect_id = 100

        mock_prospect = MagicMock(spec=Prospect)
        mock_prospect.id = 100
        mock_prospect.status = ProspectStatus.ENGAGED

        processor._get_message = AsyncMock(return_value=mock_message)
        processor._get_prospect = AsyncMock(return_value=mock_prospect)
        processor._create_engagement_event = AsyncMock()
        processor._cancel_pending_messages = AsyncMock()

        return processor, mock_message, mock_prospect

    @pytest.mark.asyncio
    async def test_handle_unsubscribe_opts_out_prospect(self, processor_with_mocks):
        """Test unsubscribe opts out prospect."""
        from api.database.outreach_models import ProspectStatus

        processor, mock_message, mock_prospect = processor_with_mocks

        event = {}
        await processor._handle_unsubscribe("1", event)

        assert mock_prospect.status == ProspectStatus.OPTED_OUT
        assert mock_prospect.email_status == "unsubscribed"
        assert mock_prospect.sequence_paused is True


class TestHandleDropped:
    """Tests for dropped event handler."""

    @pytest.mark.asyncio
    async def test_handle_dropped_marks_message_failed(self):
        """Test dropped event marks message as failed."""
        from api.services.webhook_processor import WebhookProcessor
        from api.database.outreach_models import OutreachMessage, MessageStatus

        mock_session = MagicMock()
        processor = WebhookProcessor(mock_session)

        mock_message = MagicMock(spec=OutreachMessage)
        mock_message.id = 1
        mock_message.prospect_id = 100
        mock_message.status = MessageStatus.SCHEDULED

        processor._get_message = AsyncMock(return_value=mock_message)
        processor._create_engagement_event = AsyncMock()

        event = {"reason": "Bounced address"}
        await processor._handle_dropped("1", event)

        assert mock_message.status == MessageStatus.FAILED
        assert "Dropped" in mock_message.error_message


class TestSignatureVerification:
    """Tests for SendGrid signature verification."""

    def test_verify_valid_signature(self):
        """Test valid signature verification."""
        from api.services.webhook_processor import verify_sendgrid_signature
        import hmac
        import hashlib

        webhook_key = "test-secret-key"
        timestamp = "1234567890"
        payload = b'[{"event":"open"}]'

        # Generate expected signature
        payload_to_sign = timestamp.encode() + payload
        expected_signature = hmac.new(
            webhook_key.encode(),
            payload_to_sign,
            hashlib.sha256,
        ).hexdigest()

        result = verify_sendgrid_signature(
            payload=payload,
            signature=expected_signature,
            timestamp=timestamp,
            webhook_key=webhook_key,
        )

        assert result is True

    def test_verify_invalid_signature(self):
        """Test invalid signature is rejected."""
        from api.services.webhook_processor import verify_sendgrid_signature

        result = verify_sendgrid_signature(
            payload=b'[{"event":"open"}]',
            signature="invalid-signature",
            timestamp="1234567890",
            webhook_key="test-key",
        )

        assert result is False

    def test_verify_missing_parameters(self):
        """Test verification fails with missing parameters."""
        from api.services.webhook_processor import verify_sendgrid_signature

        assert verify_sendgrid_signature(None, "sig", "ts", "key") is False
        assert verify_sendgrid_signature(b"data", None, "ts", "key") is False
        assert verify_sendgrid_signature(b"data", "sig", None, "key") is False
        assert verify_sendgrid_signature(b"data", "sig", "ts", None) is False


class TestGetMessage:
    """Tests for _get_message helper."""

    @pytest.mark.asyncio
    async def test_get_message_by_numeric_id(self):
        """Test getting message by numeric ID."""
        from api.services.webhook_processor import WebhookProcessor
        from api.database.outreach_models import OutreachMessage

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_message = MagicMock(spec=OutreachMessage)
        mock_result.scalar_one_or_none.return_value = mock_message
        mock_session.execute = AsyncMock(return_value=mock_result)

        processor = WebhookProcessor(mock_session)

        result = await processor._get_message("123")

        assert result is mock_message

    @pytest.mark.asyncio
    async def test_get_message_by_external_id(self):
        """Test getting message by external message ID."""
        from api.services.webhook_processor import WebhookProcessor
        from api.database.outreach_models import OutreachMessage

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_message = MagicMock(spec=OutreachMessage)
        mock_result.scalar_one_or_none.return_value = mock_message
        mock_session.execute = AsyncMock(return_value=mock_result)

        processor = WebhookProcessor(mock_session)

        result = await processor._get_message("sg-abc-123")

        assert result is mock_message


class TestCancelPendingMessages:
    """Tests for _cancel_pending_messages helper."""

    @pytest.mark.asyncio
    async def test_cancel_pending_messages(self):
        """Test cancelling pending messages."""
        from api.services.webhook_processor import WebhookProcessor

        mock_session = MagicMock()
        mock_session.execute = AsyncMock()

        processor = WebhookProcessor(mock_session)

        await processor._cancel_pending_messages(100)

        mock_session.execute.assert_called_once()


class TestFactoryFunction:
    """Tests for factory function."""

    def test_get_webhook_processor(self):
        """Test get_webhook_processor factory."""
        from api.services.webhook_processor import get_webhook_processor

        mock_session = MagicMock()
        processor = get_webhook_processor(mock_session)

        assert processor is not None
        assert processor.db is mock_session
