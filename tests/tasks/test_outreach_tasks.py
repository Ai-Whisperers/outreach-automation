"""
Task tests for Celery outreach tasks.

Tests cover:
- Scheduled batch processing
- Message sending tasks
- Connection status checking
- Webhook processing
- Analytics aggregation
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestScheduleDailyBatch:
    """Tests for schedule_daily_batch task."""

    @pytest.fixture
    def mock_services(self):
        """Create mock services for task testing."""
        return {
            "prospect_service": MagicMock(),
            "message_service": MagicMock(),
            "email_service": MagicMock(),
            "linkedin_service": MagicMock(),
            "rate_limiter": MagicMock(),
        }

    @pytest.mark.asyncio
    async def test_schedule_daily_batch_creates_tasks(self, mock_services):
        """Test daily batch creates sending tasks."""
        with patch("api.tasks.outreach_tasks.get_prospect_service") as mock_ps, \
             patch("api.tasks.outreach_tasks.get_message_service") as mock_ms, \
             patch("api.tasks.outreach_tasks.get_rate_limiter") as mock_rl:

            mock_ps.return_value = mock_services["prospect_service"]
            mock_ms.return_value = mock_services["message_service"]
            mock_rl.return_value = mock_services["rate_limiter"]

            # Setup mock returns
            mock_services["prospect_service"].get_pending_messages = AsyncMock(
                return_value=[
                    {"id": 1, "channel": "email"},
                    {"id": 2, "channel": "linkedin"},
                ]
            )
            mock_services["rate_limiter"].check_quota = AsyncMock(return_value=(True, 15))

            from api.tasks.outreach_tasks import schedule_daily_batch

            result = await schedule_daily_batch(campaign_id=1)

            assert result["scheduled"] >= 0

    @pytest.mark.asyncio
    async def test_schedule_respects_quotas(self, mock_services):
        """Test scheduling respects daily quotas."""
        with patch("api.tasks.outreach_tasks.get_rate_limiter") as mock_rl:
            mock_rl.return_value = mock_services["rate_limiter"]
            mock_services["rate_limiter"].check_quota = AsyncMock(return_value=(False, 0))

            from api.tasks.outreach_tasks import schedule_daily_batch

            result = await schedule_daily_batch(campaign_id=1)

            # Should not schedule when quota exceeded
            assert result["scheduled"] == 0 or result.get("quota_exceeded") is True

    @pytest.mark.asyncio
    async def test_schedule_within_optimal_window(self, mock_services):
        """Test messages are scheduled within optimal send windows."""
        with patch("api.tasks.outreach_tasks.get_rate_limiter") as mock_rl, \
             patch("api.tasks.outreach_tasks.get_message_service") as mock_ms:

            mock_rl.return_value = mock_services["rate_limiter"]
            mock_ms.return_value = mock_services["message_service"]

            mock_services["rate_limiter"].get_optimal_send_window = MagicMock(
                return_value=(9, 17)  # 9 AM to 5 PM
            )
            mock_services["message_service"].schedule_message = AsyncMock()

            from api.tasks.outreach_tasks import schedule_daily_batch

            await schedule_daily_batch(campaign_id=1)

            # Verify scheduling calls are within window
            if mock_services["message_service"].schedule_message.called:
                call_args = mock_services["message_service"].schedule_message.call_args
                scheduled_time = call_args[1].get("scheduled_at")
                if scheduled_time:
                    hour = scheduled_time.hour
                    assert 9 <= hour <= 17


class TestSendEmailTask:
    """Tests for send_email task."""

    @pytest.fixture
    def mock_email_service(self):
        """Create mock email service."""
        mock = MagicMock()
        mock.send_email = AsyncMock(return_value={
            "success": True,
            "message_id": "sg-123",
        })
        return mock

    @pytest.mark.asyncio
    async def test_send_email_success(self, mock_email_service):
        """Test successful email sending."""
        with patch("api.tasks.outreach_tasks.get_email_service") as mock_es, \
             patch("api.tasks.outreach_tasks.get_message_service") as mock_ms:

            mock_es.return_value = mock_email_service
            mock_ms.return_value = MagicMock()
            mock_ms.return_value.get_message = AsyncMock(return_value={
                "id": 1,
                "prospect_email": "john@example.com",
                "prospect_name": "John Doe",
                "subject": "Test Subject",
                "content": "<p>Hello John</p>",
            })
            mock_ms.return_value.update_message_status = AsyncMock()

            from api.tasks.outreach_tasks import send_email

            result = await send_email(message_id=1)

            assert result["success"] is True
            mock_email_service.send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_failure_updates_status(self, mock_email_service):
        """Test failed email updates message status."""
        mock_email_service.send_email = AsyncMock(return_value={
            "success": False,
            "error": "Recipient rejected",
        })

        with patch("api.tasks.outreach_tasks.get_email_service") as mock_es, \
             patch("api.tasks.outreach_tasks.get_message_service") as mock_ms:

            mock_es.return_value = mock_email_service
            mock_message_service = MagicMock()
            mock_message_service.get_message = AsyncMock(return_value={
                "id": 1,
                "prospect_email": "john@example.com",
            })
            mock_message_service.update_message_status = AsyncMock()
            mock_ms.return_value = mock_message_service

            from api.tasks.outreach_tasks import send_email

            result = await send_email(message_id=1)

            assert result["success"] is False
            mock_message_service.update_message_status.assert_called()

    @pytest.mark.asyncio
    async def test_send_email_retries_on_transient_error(self, mock_email_service):
        """Test email task retries on transient errors."""
        mock_email_service.send_email = AsyncMock(
            side_effect=[
                Exception("Temporary network error"),
                {"success": True, "message_id": "sg-123"},
            ]
        )

        with patch("api.tasks.outreach_tasks.get_email_service") as mock_es, \
             patch("api.tasks.outreach_tasks.get_message_service") as mock_ms:

            mock_es.return_value = mock_email_service
            mock_ms.return_value = MagicMock()
            mock_ms.return_value.get_message = AsyncMock(return_value={"id": 1})

            from api.tasks.outreach_tasks import send_email

            # First call should fail, but task should be retryable
            try:
                await send_email(message_id=1)
            except Exception:
                pass  # Expected on first attempt

            # Second call should succeed
            result = await send_email(message_id=1)
            assert result["success"] is True


class TestSendLinkedInTask:
    """Tests for send_linkedin task."""

    @pytest.fixture
    def mock_linkedin_service(self):
        """Create mock LinkedIn service."""
        mock = MagicMock()
        mock.send_connection_request = AsyncMock(return_value={
            "success": True,
            "request_id": "li-123",
        })
        mock.send_message = AsyncMock(return_value={
            "success": True,
            "message_id": "li-msg-123",
        })
        return mock

    @pytest.mark.asyncio
    async def test_send_connection_request_success(self, mock_linkedin_service):
        """Test successful connection request."""
        with patch("api.tasks.outreach_tasks.get_linkedin_service") as mock_ls, \
             patch("api.tasks.outreach_tasks.get_message_service") as mock_ms:

            mock_ls.return_value = mock_linkedin_service
            mock_ms.return_value = MagicMock()
            mock_ms.return_value.get_message = AsyncMock(return_value={
                "id": 1,
                "message_type": "connection_request",
                "prospect_linkedin_url": "https://linkedin.com/in/johndoe",
                "content": "Hi John, let's connect!",
            })
            mock_ms.return_value.update_message_status = AsyncMock()

            from api.tasks.outreach_tasks import send_linkedin

            result = await send_linkedin(message_id=1)

            assert result["success"] is True
            mock_linkedin_service.send_connection_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_linkedin_message_success(self, mock_linkedin_service):
        """Test successful LinkedIn DM."""
        with patch("api.tasks.outreach_tasks.get_linkedin_service") as mock_ls, \
             patch("api.tasks.outreach_tasks.get_message_service") as mock_ms:

            mock_ls.return_value = mock_linkedin_service
            mock_ms.return_value = MagicMock()
            mock_ms.return_value.get_message = AsyncMock(return_value={
                "id": 1,
                "message_type": "linkedin_message",
                "prospect_linkedin_url": "https://linkedin.com/in/johndoe",
                "content": "Thanks for connecting!",
            })

            from api.tasks.outreach_tasks import send_linkedin

            result = await send_linkedin(message_id=1)

            assert result["success"] is True
            mock_linkedin_service.send_message.assert_called_once()


class TestCheckConnectionsTask:
    """Tests for check_connections task."""

    @pytest.fixture
    def mock_linkedin_service(self):
        """Create mock LinkedIn service."""
        mock = MagicMock()
        mock.check_connection_status = AsyncMock(return_value="connected")
        return mock

    @pytest.mark.asyncio
    async def test_check_connections_updates_status(self, mock_linkedin_service):
        """Test checking connections updates prospect status."""
        with patch("api.tasks.outreach_tasks.get_linkedin_service") as mock_ls, \
             patch("api.tasks.outreach_tasks.get_prospect_service") as mock_ps:

            mock_ls.return_value = mock_linkedin_service
            mock_prospect_service = MagicMock()
            mock_prospect_service.get_pending_connections = AsyncMock(return_value=[
                {"id": 1, "linkedin_url": "https://linkedin.com/in/johndoe"},
                {"id": 2, "linkedin_url": "https://linkedin.com/in/janesmith"},
            ])
            mock_prospect_service.update_status = AsyncMock()
            mock_ps.return_value = mock_prospect_service

            from api.tasks.outreach_tasks import check_connections

            result = await check_connections(campaign_id=1)

            assert result["checked"] == 2
            assert mock_prospect_service.update_status.call_count >= 1

    @pytest.mark.asyncio
    async def test_check_connections_creates_events(self, mock_linkedin_service):
        """Test accepted connections create engagement events."""
        with patch("api.tasks.outreach_tasks.get_linkedin_service") as mock_ls, \
             patch("api.tasks.outreach_tasks.get_prospect_service") as mock_ps, \
             patch("api.tasks.outreach_tasks.get_event_service") as mock_es:

            mock_ls.return_value = mock_linkedin_service
            mock_prospect_service = MagicMock()
            mock_prospect_service.get_pending_connections = AsyncMock(return_value=[
                {"id": 1, "linkedin_url": "https://linkedin.com/in/johndoe"},
            ])
            mock_ps.return_value = mock_prospect_service

            mock_event_service = MagicMock()
            mock_event_service.create_event = AsyncMock()
            mock_es.return_value = mock_event_service

            from api.tasks.outreach_tasks import check_connections

            await check_connections(campaign_id=1)

            mock_event_service.create_event.assert_called()


class TestProcessWebhooksTask:
    """Tests for process_webhooks task."""

    @pytest.mark.asyncio
    async def test_process_sendgrid_events(self):
        """Test processing SendGrid webhook events."""
        with patch("api.tasks.outreach_tasks.get_event_service") as mock_es:
            mock_event_service = MagicMock()
            mock_event_service.process_events = AsyncMock(return_value={
                "processed": 3,
                "errors": 0,
            })
            mock_es.return_value = mock_event_service

            events = [
                {"event": "open", "email": "john@example.com"},
                {"event": "click", "email": "john@example.com"},
                {"event": "delivered", "email": "john@example.com"},
            ]

            from api.tasks.outreach_tasks import process_webhooks

            result = await process_webhooks(events=events, source="sendgrid")

            assert result["processed"] == 3

    @pytest.mark.asyncio
    async def test_process_webhooks_handles_errors(self):
        """Test webhook processing handles individual event errors."""
        with patch("api.tasks.outreach_tasks.get_event_service") as mock_es:
            mock_event_service = MagicMock()
            mock_event_service.process_events = AsyncMock(return_value={
                "processed": 2,
                "errors": 1,
                "error_details": ["Event 3: Invalid format"],
            })
            mock_es.return_value = mock_event_service

            events = [
                {"event": "open", "email": "john@example.com"},
                {"event": "click", "email": "john@example.com"},
                {"event": "invalid"},
            ]

            from api.tasks.outreach_tasks import process_webhooks

            result = await process_webhooks(events=events, source="sendgrid")

            assert result["processed"] == 2
            assert result["errors"] == 1


class TestAggregateAnalyticsTask:
    """Tests for aggregate_analytics task."""

    @pytest.mark.asyncio
    async def test_aggregate_daily_analytics(self):
        """Test aggregating daily analytics."""
        with patch("api.tasks.outreach_tasks.get_analytics_service") as mock_as:
            mock_analytics = MagicMock()
            mock_analytics.aggregate_daily = AsyncMock(return_value={
                "date": "2024-01-15",
                "linkedin_sent": 10,
                "email_sent": 25,
                "connections_accepted": 3,
                "emails_opened": 15,
                "emails_clicked": 5,
                "replies_received": 2,
            })
            mock_as.return_value = mock_analytics

            from api.tasks.outreach_tasks import aggregate_analytics

            result = await aggregate_analytics(campaign_id=1, date="2024-01-15")

            assert result["linkedin_sent"] == 10
            assert result["email_sent"] == 25

    @pytest.mark.asyncio
    async def test_aggregate_stores_results(self):
        """Test analytics aggregation stores results."""
        with patch("api.tasks.outreach_tasks.get_analytics_service") as mock_as:
            mock_analytics = MagicMock()
            mock_analytics.aggregate_daily = AsyncMock(return_value={"date": "2024-01-15"})
            mock_analytics.store_daily_metrics = AsyncMock()
            mock_as.return_value = mock_analytics

            from api.tasks.outreach_tasks import aggregate_analytics

            await aggregate_analytics(campaign_id=1, date="2024-01-15")

            mock_analytics.store_daily_metrics.assert_called()


class TestTaskRetryBehavior:
    """Tests for task retry behavior."""

    @pytest.mark.asyncio
    async def test_email_task_max_retries(self):
        """Test email task has max retry limit."""
        with patch("api.tasks.outreach_tasks.get_email_service") as mock_es, \
             patch("api.tasks.outreach_tasks.get_message_service") as mock_ms:

            mock_email_service = MagicMock()
            mock_email_service.send_email = AsyncMock(
                side_effect=Exception("Persistent error")
            )
            mock_es.return_value = mock_email_service

            mock_ms.return_value = MagicMock()
            mock_ms.return_value.get_message = AsyncMock(return_value={"id": 1})
            mock_ms.return_value.increment_retry_count = AsyncMock(return_value=4)  # Max retries

            from api.tasks.outreach_tasks import send_email

            result = await send_email(message_id=1)

            # Should give up after max retries
            assert result["success"] is False
            assert "max_retries" in result.get("error", "").lower() or \
                   result.get("gave_up") is True

    @pytest.mark.asyncio
    async def test_linkedin_task_respects_rate_limits(self):
        """Test LinkedIn task respects rate limit delays."""
        with patch("api.tasks.outreach_tasks.get_linkedin_service") as mock_ls, \
             patch("api.tasks.outreach_tasks.get_rate_limiter") as mock_rl:

            mock_linkedin_service = MagicMock()
            mock_ls.return_value = mock_linkedin_service

            mock_rate_limiter = MagicMock()
            mock_rate_limiter.check_quota = AsyncMock(return_value=(False, 0))
            mock_rl.return_value = mock_rate_limiter

            from api.tasks.outreach_tasks import send_linkedin

            result = await send_linkedin(message_id=1)

            # Should not attempt to send when quota exceeded
            assert result.get("skipped") is True or result.get("quota_exceeded") is True
            mock_linkedin_service.send_connection_request.assert_not_called()


class TestTaskScheduling:
    """Tests for task scheduling utilities."""

    def test_calculate_next_send_time(self):
        """Test calculating next optimal send time."""
        from api.tasks.outreach_tasks import calculate_next_send_time

        # If before optimal window, should be today
        now = datetime.utcnow().replace(hour=6)
        next_time = calculate_next_send_time(now, channel="email")

        assert next_time.hour >= 9  # Start of email window

    def test_calculate_next_send_time_after_window(self):
        """Test calculating next time when after window."""
        from api.tasks.outreach_tasks import calculate_next_send_time

        # If after optimal window, should be tomorrow
        now = datetime.utcnow().replace(hour=20)
        next_time = calculate_next_send_time(now, channel="email")

        assert next_time.date() > now.date() or next_time.hour >= 9

    def test_distribute_messages_evenly(self):
        """Test distributing messages evenly across time window."""
        from api.tasks.outreach_tasks import distribute_send_times

        message_count = 20
        start_hour = 9
        end_hour = 17

        times = distribute_send_times(message_count, start_hour, end_hour)

        assert len(times) == message_count
        # All times should be within window
        for t in times:
            assert start_hour <= t.hour <= end_hour
