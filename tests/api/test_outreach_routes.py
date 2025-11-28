"""
API tests for outreach execution routes.

Tests cover:
- Scheduling messages
- Starting/pausing outreach
- Quota status
- Webhook handling
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class TestOutreachRoutes:
    """Tests for outreach execution API endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.outreach.get_outreach_service") as mock_os, \
             patch("api.routes.outreach.get_rate_limiter") as mock_rl:

            mock_outreach_service = MagicMock()
            mock_rate_limiter = MagicMock()
            mock_os.return_value = mock_outreach_service
            mock_rl.return_value = mock_rate_limiter

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_outreach_service, mock_rate_limiter

    @pytest.fixture
    def sample_outreach_status(self):
        """Sample outreach status response."""
        return {
            "campaign_id": 1,
            "is_active": True,
            "started_at": "2024-01-01T00:00:00",
            "paused_at": None,
            "today_linkedin_sent": 5,
            "today_linkedin_remaining": 15,
            "today_email_sent": 10,
            "today_email_remaining": 40,
            "total_scheduled": 50,
            "total_sent": 100,
        }

    @pytest.mark.asyncio
    async def test_schedule_message(self, client):
        """Test scheduling a message for sending."""
        test_client, mock_os, mock_rl = client
        mock_os.schedule_message = AsyncMock(return_value={
            "message_id": 1,
            "scheduled_at": "2024-01-15T10:00:00",
            "status": "scheduled",
        })

        response = await test_client.post(
            "/outreach/schedule",
            json={
                "message_id": 1,
                "scheduled_at": "2024-01-15T10:00:00",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scheduled"

    @pytest.mark.asyncio
    async def test_schedule_batch(self, client):
        """Test batch scheduling messages."""
        test_client, mock_os, mock_rl = client
        mock_os.schedule_batch = AsyncMock(return_value={
            "scheduled_count": 10,
            "failed_count": 0,
            "next_available_slot": "2024-01-15T10:00:00",
        })

        response = await test_client.post(
            "/outreach/schedule/batch",
            json={
                "campaign_id": 1,
                "message_ids": [1, 2, 3, 4, 5],
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["scheduled_count"] == 10

    @pytest.mark.asyncio
    async def test_start_outreach(self, client, sample_outreach_status):
        """Test starting outreach for a campaign."""
        test_client, mock_os, mock_rl = client
        mock_os.start_outreach = AsyncMock(return_value=sample_outreach_status)

        response = await test_client.post(
            "/outreach/start",
            json={
                "campaign_id": 1,
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_start_outreach_specific_channels(self, client, sample_outreach_status):
        """Test starting outreach for specific channels."""
        test_client, mock_os, mock_rl = client
        mock_os.start_outreach = AsyncMock(return_value=sample_outreach_status)

        response = await test_client.post(
            "/outreach/start",
            json={
                "campaign_id": 1,
                "channels": ["email"],
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        mock_os.start_outreach.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_outreach_specific_prospects(self, client, sample_outreach_status):
        """Test starting outreach for specific prospects."""
        test_client, mock_os, mock_rl = client
        mock_os.start_outreach = AsyncMock(return_value=sample_outreach_status)

        response = await test_client.post(
            "/outreach/start",
            json={
                "campaign_id": 1,
                "prospect_ids": [1, 2, 3],
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_pause_outreach(self, client, sample_outreach_status):
        """Test pausing outreach."""
        test_client, mock_os, mock_rl = client
        paused = {**sample_outreach_status, "is_active": False, "paused_at": "2024-01-15T12:00:00"}
        mock_os.pause_outreach = AsyncMock(return_value=paused)

        response = await test_client.post(
            "/outreach/pause",
            json={
                "campaign_id": 1,
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_pause_outreach_cancel_scheduled(self, client, sample_outreach_status):
        """Test pausing outreach and cancelling scheduled messages."""
        test_client, mock_os, mock_rl = client
        paused = {**sample_outreach_status, "is_active": False}
        mock_os.pause_outreach = AsyncMock(return_value=paused)

        response = await test_client.post(
            "/outreach/pause",
            json={
                "campaign_id": 1,
                "cancel_scheduled": True,
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        call_kwargs = mock_os.pause_outreach.call_args[1]
        assert call_kwargs.get("cancel_scheduled") is True

    @pytest.mark.asyncio
    async def test_get_outreach_status(self, client, sample_outreach_status):
        """Test getting outreach status."""
        test_client, mock_os, mock_rl = client
        mock_os.get_status = AsyncMock(return_value=sample_outreach_status)

        response = await test_client.get("/outreach/1/status")

        assert response.status_code == 200
        data = response.json()
        assert data["campaign_id"] == 1
        assert data["today_linkedin_remaining"] == 15

    @pytest.mark.asyncio
    async def test_get_outreach_status_not_found(self, client):
        """Test getting status for non-existent campaign."""
        test_client, mock_os, mock_rl = client
        mock_os.get_status = AsyncMock(return_value=None)

        response = await test_client.get("/outreach/999/status")

        assert response.status_code == 404


class TestQuotaEndpoints:
    """Tests for quota-related endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.outreach.get_rate_limiter") as mock_rl:
            mock_rate_limiter = MagicMock()
            mock_rl.return_value = mock_rate_limiter

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_rate_limiter

    @pytest.mark.asyncio
    async def test_get_quota_status(self, client):
        """Test getting quota status."""
        test_client, mock_rl = client
        mock_rl.get_quota_status = AsyncMock(return_value={
            "date": "2024-01-15",
            "campaign_id": 1,
            "channels": {
                "linkedin_connection": {
                    "used": 5,
                    "limit": 20,
                    "remaining": 15,
                    "percentage": 25,
                },
                "email": {
                    "used": 10,
                    "limit": 50,
                    "remaining": 40,
                    "percentage": 20,
                },
            },
        })

        response = await test_client.get("/outreach/1/quota")

        assert response.status_code == 200
        data = response.json()
        assert data["channels"]["linkedin_connection"]["remaining"] == 15

    @pytest.mark.asyncio
    async def test_check_quota_before_send(self, client):
        """Test checking quota before sending."""
        test_client, mock_rl = client
        mock_rl.check_quota = AsyncMock(return_value=(True, 15))

        response = await test_client.get("/outreach/1/quota/check?channel=linkedin_connection")

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is True
        assert data["remaining"] == 15

    @pytest.mark.asyncio
    async def test_check_quota_exceeded(self, client):
        """Test checking quota when exceeded."""
        test_client, mock_rl = client
        mock_rl.check_quota = AsyncMock(return_value=(False, 0))

        response = await test_client.get("/outreach/1/quota/check?channel=linkedin_connection")

        assert response.status_code == 200
        data = response.json()
        assert data["allowed"] is False
        assert data["remaining"] == 0


class TestWebhookEndpoints:
    """Tests for webhook handling endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.outreach.get_webhook_handler") as mock_wh:
            mock_webhook_handler = MagicMock()
            mock_wh.return_value = mock_webhook_handler

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_webhook_handler

    @pytest.mark.asyncio
    async def test_sendgrid_webhook_open(self, client):
        """Test handling SendGrid open event."""
        test_client, mock_wh = client
        mock_wh.process_sendgrid_events = AsyncMock(return_value={
            "status": "ok",
            "events_processed": 1,
        })

        response = await test_client.post(
            "/outreach/webhooks/sendgrid",
            json=[{
                "event": "open",
                "email": "john@example.com",
                "timestamp": 1705000000,
                "sg_message_id": "abc123",
            }],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_sendgrid_webhook_click(self, client):
        """Test handling SendGrid click event."""
        test_client, mock_wh = client
        mock_wh.process_sendgrid_events = AsyncMock(return_value={
            "status": "ok",
            "events_processed": 1,
        })

        response = await test_client.post(
            "/outreach/webhooks/sendgrid",
            json=[{
                "event": "click",
                "email": "john@example.com",
                "url": "https://example.com/link",
                "timestamp": 1705000000,
            }],
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_sendgrid_webhook_bounce(self, client):
        """Test handling SendGrid bounce event."""
        test_client, mock_wh = client
        mock_wh.process_sendgrid_events = AsyncMock(return_value={
            "status": "ok",
            "events_processed": 1,
        })

        response = await test_client.post(
            "/outreach/webhooks/sendgrid",
            json=[{
                "event": "bounce",
                "email": "john@example.com",
                "reason": "Invalid address",
            }],
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_sendgrid_webhook_batch(self, client):
        """Test handling multiple SendGrid events."""
        test_client, mock_wh = client
        mock_wh.process_sendgrid_events = AsyncMock(return_value={
            "status": "ok",
            "events_processed": 3,
        })

        response = await test_client.post(
            "/outreach/webhooks/sendgrid",
            json=[
                {"event": "delivered", "email": "john@example.com"},
                {"event": "open", "email": "john@example.com"},
                {"event": "click", "email": "john@example.com"},
            ],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["events_processed"] == 3


class TestOutreachRoutesErrorHandling:
    """Tests for error handling in outreach routes."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.outreach.get_outreach_service") as mock_os:
            mock_service = MagicMock()
            mock_os.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.mark.asyncio
    async def test_schedule_server_error(self, client):
        """Test server error during scheduling."""
        test_client, mock_service = client
        mock_service.schedule_message = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = await test_client.post(
            "/outreach/schedule",
            json={
                "message_id": 1,
                "scheduled_at": "2024-01-15T10:00:00",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_start_outreach_no_messages(self, client):
        """Test starting outreach with no approved messages."""
        test_client, mock_service = client
        mock_service.start_outreach = AsyncMock(return_value={
            "error": "No approved messages to send",
        })

        response = await test_client.post(
            "/outreach/start",
            json={"campaign_id": 1},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_start_outreach_campaign_not_found(self, client):
        """Test starting outreach for non-existent campaign."""
        test_client, mock_service = client
        mock_service.start_outreach = AsyncMock(return_value=None)

        response = await test_client.post(
            "/outreach/start",
            json={"campaign_id": 999},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_quota_exceeded_error(self, client):
        """Test error when quota is exceeded."""
        test_client, mock_service = client
        mock_service.schedule_message = AsyncMock(return_value={
            "error": "Daily quota exceeded for linkedin_connection",
        })

        response = await test_client.post(
            "/outreach/schedule",
            json={
                "message_id": 1,
                "scheduled_at": "2024-01-15T10:00:00",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 429  # Too Many Requests
