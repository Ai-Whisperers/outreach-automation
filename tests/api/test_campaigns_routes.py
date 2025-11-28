"""
API tests for campaign routes.

Tests cover:
- CRUD operations
- Campaign activation/pause
- Analytics
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class TestCampaignRoutes:
    """Tests for campaign API endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.campaigns.get_prospect_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service_factory.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.fixture
    def sample_campaign_response(self):
        """Sample campaign response data."""
        return {
            "id": 1,
            "name": "Test Campaign",
            "description": "Test description",
            "channels": ["linkedin", "email"],
            "daily_linkedin_limit": 20,
            "daily_email_limit": 50,
            "is_active": False,
            "prospect_count": 0,
            "message_count": 0,
            "created_at": "2024-01-01T00:00:00",
            "started_at": None,
            "paused_at": None,
        }

    @pytest.mark.asyncio
    async def test_create_campaign(self, client, sample_campaign_response):
        """Test creating a new campaign."""
        test_client, mock_service = client
        mock_service.create_campaign = AsyncMock(return_value=sample_campaign_response)

        response = await test_client.post(
            "/campaigns",
            json={
                "name": "Test Campaign",
                "description": "Test description",
                "channels": ["linkedin", "email"],
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Campaign"

    @pytest.mark.asyncio
    async def test_create_campaign_minimal(self, client, sample_campaign_response):
        """Test creating campaign with minimal fields."""
        test_client, mock_service = client
        mock_service.create_campaign = AsyncMock(return_value=sample_campaign_response)

        response = await test_client.post(
            "/campaigns",
            json={"name": "Minimal Campaign"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_campaign_invalid_name(self, client):
        """Test creating campaign with invalid name."""
        test_client, mock_service = client

        response = await test_client.post(
            "/campaigns",
            json={"name": ""},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_list_campaigns(self, client, sample_campaign_response):
        """Test listing campaigns."""
        test_client, mock_service = client
        mock_service.list_campaigns = AsyncMock(return_value={
            "items": [sample_campaign_response],
            "total": 1,
        })

        response = await test_client.get("/campaigns")

        assert response.status_code == 200
        data = response.json()
        assert len(data["campaigns"]) == 1
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_campaigns_with_pagination(self, client, sample_campaign_response):
        """Test listing campaigns with pagination."""
        test_client, mock_service = client
        mock_service.list_campaigns = AsyncMock(return_value={
            "items": [sample_campaign_response],
            "total": 10,
        })

        response = await test_client.get("/campaigns?skip=5&limit=5")

        assert response.status_code == 200
        mock_service.list_campaigns.assert_called_once()
        call_kwargs = mock_service.list_campaigns.call_args[1]
        assert call_kwargs["skip"] == 5
        assert call_kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_list_campaigns_with_status_filter(self, client, sample_campaign_response):
        """Test listing campaigns with status filter."""
        test_client, mock_service = client
        mock_service.list_campaigns = AsyncMock(return_value={
            "items": [sample_campaign_response],
            "total": 1,
        })

        response = await test_client.get("/campaigns?status=active")

        assert response.status_code == 200
        call_kwargs = mock_service.list_campaigns.call_args[1]
        assert call_kwargs["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_campaign(self, client, sample_campaign_response):
        """Test getting a single campaign."""
        test_client, mock_service = client
        mock_service.get_campaign = AsyncMock(return_value=sample_campaign_response)

        response = await test_client.get("/campaigns/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test Campaign"

    @pytest.mark.asyncio
    async def test_get_campaign_not_found(self, client):
        """Test getting non-existent campaign."""
        test_client, mock_service = client
        mock_service.get_campaign = AsyncMock(return_value=None)

        response = await test_client.get("/campaigns/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_campaign(self, client, sample_campaign_response):
        """Test updating a campaign."""
        test_client, mock_service = client
        updated = {**sample_campaign_response, "name": "Updated Name"}
        mock_service.update_campaign = AsyncMock(return_value=updated)

        response = await test_client.patch(
            "/campaigns/1",
            json={"name": "Updated Name"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_campaign_not_found(self, client):
        """Test updating non-existent campaign."""
        test_client, mock_service = client
        mock_service.update_campaign = AsyncMock(return_value=None)

        response = await test_client.patch(
            "/campaigns/999",
            json={"name": "Updated"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_campaign_no_fields(self, client):
        """Test updating campaign with no fields."""
        test_client, mock_service = client

        response = await test_client.patch(
            "/campaigns/1",
            json={},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 400
        assert "No update fields" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_campaign(self, client):
        """Test deleting a campaign."""
        test_client, mock_service = client
        mock_service.delete_campaign = AsyncMock(return_value=True)

        response = await test_client.delete(
            "/campaigns/1",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_campaign_not_found(self, client):
        """Test deleting non-existent campaign."""
        test_client, mock_service = client
        mock_service.delete_campaign = AsyncMock(return_value=False)

        response = await test_client.delete(
            "/campaigns/999",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_activate_campaign(self, client, sample_campaign_response):
        """Test activating a campaign."""
        test_client, mock_service = client
        activated = {**sample_campaign_response, "is_active": True}
        mock_service.activate_campaign = AsyncMock(return_value=activated)

        response = await test_client.post(
            "/campaigns/1/activate",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_activate_campaign_not_found(self, client):
        """Test activating non-existent campaign."""
        test_client, mock_service = client
        mock_service.activate_campaign = AsyncMock(return_value=None)

        response = await test_client.post(
            "/campaigns/999/activate",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_activate_campaign_error(self, client):
        """Test activating campaign with error."""
        test_client, mock_service = client
        mock_service.activate_campaign = AsyncMock(return_value={
            "error": "Campaign has no prospects",
        })

        response = await test_client.post(
            "/campaigns/1/activate",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 400
        assert "no prospects" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_pause_campaign(self, client, sample_campaign_response):
        """Test pausing a campaign."""
        test_client, mock_service = client
        paused = {**sample_campaign_response, "is_active": False}
        mock_service.pause_campaign = AsyncMock(return_value=paused)

        response = await test_client.post(
            "/campaigns/1/pause",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_get_campaign_analytics(self, client):
        """Test getting campaign analytics."""
        test_client, mock_service = client
        mock_service.get_campaign_analytics = AsyncMock(return_value={
            "campaign_id": 1,
            "total_prospects": 100,
            "total_sent": 50,
            "linkedin_sent": 20,
            "email_sent": 30,
            "connections_accepted": 10,
            "connection_rate": 0.5,
            "emails_opened": 20,
            "open_rate": 0.67,
            "emails_clicked": 8,
            "click_rate": 0.27,
            "replies_received": 5,
            "reply_rate": 0.10,
        })

        response = await test_client.get("/campaigns/1/analytics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_prospects"] == 100
        assert data["connection_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_get_campaign_analytics_not_found(self, client):
        """Test getting analytics for non-existent campaign."""
        test_client, mock_service = client
        mock_service.get_campaign_analytics = AsyncMock(return_value=None)

        response = await test_client.get("/campaigns/999/analytics")

        assert response.status_code == 404


class TestCampaignRoutesErrorHandling:
    """Tests for error handling in campaign routes."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.campaigns.get_prospect_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service_factory.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.mark.asyncio
    async def test_create_campaign_server_error(self, client):
        """Test server error during campaign creation."""
        test_client, mock_service = client
        mock_service.create_campaign = AsyncMock(side_effect=Exception("Database error"))

        response = await test_client.post(
            "/campaigns",
            json={"name": "Test"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 500
        assert "Failed to create" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_campaigns_server_error(self, client):
        """Test server error during campaign listing."""
        test_client, mock_service = client
        mock_service.list_campaigns = AsyncMock(side_effect=Exception("Database error"))

        response = await test_client.get("/campaigns")

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_campaign_server_error(self, client):
        """Test server error during campaign retrieval."""
        test_client, mock_service = client
        mock_service.get_campaign = AsyncMock(side_effect=Exception("Database error"))

        response = await test_client.get("/campaigns/1")

        assert response.status_code == 500
