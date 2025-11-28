"""
API tests for message routes.

Tests cover:
- Message generation
- Message preview
- Message editing and approval
- Batch operations
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class TestMessageRoutes:
    """Tests for message API endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.messages.get_prospect_service") as mock_ps, \
             patch("api.routes.messages.get_message_service") as mock_ms:

            mock_prospect_service = MagicMock()
            mock_message_service = MagicMock()
            mock_ps.return_value = mock_prospect_service
            mock_ms.return_value = mock_message_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_prospect_service, mock_message_service

    @pytest.fixture
    def sample_message_response(self):
        """Sample message response data."""
        return {
            "id": 1,
            "prospect_id": 1,
            "prospect_name": "John Doe",
            "company": "Acme Corp",
            "channel": "email",
            "message_type": "email_initial",
            "subject": "Quick question about Acme",
            "content": "Hi John, I noticed Acme's growth...",
            "character_count": 150,
            "word_count": 25,
            "personalization_score": 0.85,
            "status": "draft",
            "scheduled_at": None,
            "sent_at": None,
            "created_at": "2024-01-01T00:00:00",
        }

    @pytest.fixture
    def sample_generation_response(self):
        """Sample message generation response."""
        return {
            "prospect_id": 1,
            "prospect_name": "John Doe",
            "company": "Acme Corp",
            "icp_type": "sme",
            "language": "en",
            "linkedin_connection": {
                "message": "Hi John, noticed your work at Acme. Worth connecting?",
                "character_count": 52,
                "personalization_elements": ["first_name", "company"],
                "validation_passed": True,
            },
            "cold_email": {
                "subject": "Quick question about Acme",
                "body": "Hi John, I noticed...",
                "word_count": 150,
                "personalization_score": 0.85,
                "personalization_elements": ["first_name", "company", "pain_point"],
            },
            "messages_created": 2,
            "generation_time_ms": 1500,
        }

    @pytest.mark.asyncio
    async def test_generate_messages(self, client, sample_generation_response):
        """Test generating messages for prospects."""
        test_client, mock_ps, mock_ms = client
        mock_ms.generate_messages = AsyncMock(return_value=[sample_generation_response])

        response = await test_client.post(
            "/messages/generate",
            json={
                "campaign_id": 1,
                "message_types": ["connection_request", "email_initial"],
                "language": "en",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["messages_created"] == 2

    @pytest.mark.asyncio
    async def test_generate_messages_for_prospect(self, client, sample_generation_response):
        """Test generating messages for a specific prospect."""
        test_client, mock_ps, mock_ms = client
        mock_ms.generate_for_prospect = AsyncMock(return_value=sample_generation_response)

        response = await test_client.post(
            "/messages/generate/1",
            json={
                "message_types": ["email_initial"],
                "language": "en",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["prospect_id"] == 1

    @pytest.mark.asyncio
    async def test_generate_messages_with_icp_override(self, client, sample_generation_response):
        """Test generating messages with ICP override."""
        test_client, mock_ps, mock_ms = client
        mock_ms.generate_for_prospect = AsyncMock(return_value=sample_generation_response)

        response = await test_client.post(
            "/messages/generate/1",
            json={
                "message_types": ["email_initial"],
                "icp_override": "enterprise",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        mock_ms.generate_for_prospect.assert_called_once()

    @pytest.mark.asyncio
    async def test_preview_message(self, client):
        """Test previewing a message before generation."""
        test_client, mock_ps, mock_ms = client
        mock_ms.preview_message = AsyncMock(return_value={
            "prospect_id": 1,
            "message_type": "email_initial",
            "preview": "Hi John, I noticed...",
            "personalization_elements": ["first_name"],
        })

        response = await test_client.post(
            "/messages/1/preview",
            json={
                "message_type": "email_initial",
                "language": "en",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "preview" in data

    @pytest.mark.asyncio
    async def test_get_message(self, client, sample_message_response):
        """Test getting a single message."""
        test_client, mock_ps, mock_ms = client
        mock_ms.get_message = AsyncMock(return_value=sample_message_response)

        response = await test_client.get("/messages/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["status"] == "draft"

    @pytest.mark.asyncio
    async def test_get_message_not_found(self, client):
        """Test getting non-existent message."""
        test_client, mock_ps, mock_ms = client
        mock_ms.get_message = AsyncMock(return_value=None)

        response = await test_client.get("/messages/999")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_edit_message(self, client, sample_message_response):
        """Test editing a message."""
        test_client, mock_ps, mock_ms = client
        updated = {**sample_message_response, "content": "Updated content"}
        mock_ms.update_message = AsyncMock(return_value=updated)

        response = await test_client.put(
            "/messages/1",
            json={
                "content": "Updated content",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated content"

    @pytest.mark.asyncio
    async def test_edit_message_subject(self, client, sample_message_response):
        """Test editing message subject."""
        test_client, mock_ps, mock_ms = client
        updated = {**sample_message_response, "subject": "New subject"}
        mock_ms.update_message = AsyncMock(return_value=updated)

        response = await test_client.put(
            "/messages/1",
            json={
                "subject": "New subject",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["subject"] == "New subject"

    @pytest.mark.asyncio
    async def test_edit_message_not_found(self, client):
        """Test editing non-existent message."""
        test_client, mock_ps, mock_ms = client
        mock_ms.update_message = AsyncMock(return_value=None)

        response = await test_client.put(
            "/messages/999",
            json={"content": "Test"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_messages(self, client):
        """Test approving messages for sending."""
        test_client, mock_ps, mock_ms = client
        mock_ms.approve_messages = AsyncMock(return_value={
            "approved_count": 3,
            "failed_count": 0,
            "errors": [],
        })

        response = await test_client.post(
            "/messages/approve",
            json={
                "message_ids": [1, 2, 3],
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["approved_count"] == 3

    @pytest.mark.asyncio
    async def test_approve_messages_partial_failure(self, client):
        """Test approving messages with some failures."""
        test_client, mock_ps, mock_ms = client
        mock_ms.approve_messages = AsyncMock(return_value={
            "approved_count": 2,
            "failed_count": 1,
            "errors": ["Message 3: validation failed"],
        })

        response = await test_client.post(
            "/messages/approve",
            json={
                "message_ids": [1, 2, 3],
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["approved_count"] == 2
        assert data["failed_count"] == 1

    @pytest.mark.asyncio
    async def test_list_campaign_messages(self, client, sample_message_response):
        """Test listing messages for a campaign."""
        test_client, mock_ps, mock_ms = client
        mock_ms.list_campaign_messages = AsyncMock(return_value={
            "messages": [sample_message_response],
            "total": 1,
        })

        response = await test_client.get("/campaigns/1/messages")

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1

    @pytest.mark.asyncio
    async def test_list_campaign_messages_with_filters(self, client, sample_message_response):
        """Test listing campaign messages with filters."""
        test_client, mock_ps, mock_ms = client
        mock_ms.list_campaign_messages = AsyncMock(return_value={
            "messages": [sample_message_response],
            "total": 1,
        })

        response = await test_client.get(
            "/campaigns/1/messages?status=draft&channel=email"
        )

        assert response.status_code == 200
        call_kwargs = mock_ms.list_campaign_messages.call_args[1]
        assert call_kwargs.get("status") == "draft"
        assert call_kwargs.get("channel") == "email"


class TestMessageValidation:
    """Tests for message validation endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.messages.get_message_validator") as mock_mv:
            mock_validator = MagicMock()
            mock_mv.return_value = mock_validator

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_validator

    @pytest.mark.asyncio
    async def test_validate_message(self, client):
        """Test validating a message."""
        test_client, mock_validator = client
        mock_validator.validate_message = MagicMock(return_value={
            "is_valid": True,
            "overall_score": 0.85,
            "length": {"is_valid": True},
            "tone": {"is_appropriate": True},
            "cta": {"has_cta": True},
            "issues": [],
            "suggestions": [],
        })

        response = await test_client.post(
            "/messages/validate",
            json={
                "message": "Hi John, noticed your work at Acme. Worth connecting?",
                "message_type": "connection_request",
                "icp_type": "sme",
                "language": "en",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["overall_score"] >= 0.8

    @pytest.mark.asyncio
    async def test_validate_message_invalid(self, client):
        """Test validating an invalid message."""
        test_client, mock_validator = client
        mock_validator.validate_message = MagicMock(return_value={
            "is_valid": False,
            "overall_score": 0.4,
            "length": {"is_valid": False, "issue": "Too long"},
            "cta": {"has_cta": False},
            "issues": ["Too long", "Missing CTA"],
            "suggestions": ["Shorten message", "Add call-to-action"],
        })

        response = await test_client.post(
            "/messages/validate",
            json={
                "message": "x" * 300,
                "message_type": "connection_request",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert len(data["issues"]) > 0


class TestMessageBatchOperations:
    """Tests for batch message operations."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.messages.get_message_service") as mock_ms:
            mock_service = MagicMock()
            mock_ms.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.mark.asyncio
    async def test_batch_generate(self, client):
        """Test batch message generation."""
        test_client, mock_service = client
        mock_service.batch_generate = AsyncMock(return_value={
            "campaign_id": 1,
            "prospects_processed": 10,
            "messages_generated": 20,
            "errors": [],
        })

        response = await test_client.post(
            "/messages/batch/generate",
            json={
                "campaign_id": 1,
                "message_types": ["connection_request", "email_initial"],
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["prospects_processed"] == 10
        assert data["messages_generated"] == 20

    @pytest.mark.asyncio
    async def test_batch_generate_with_prospect_ids(self, client):
        """Test batch generation for specific prospects."""
        test_client, mock_service = client
        mock_service.batch_generate = AsyncMock(return_value={
            "campaign_id": 1,
            "prospects_processed": 3,
            "messages_generated": 6,
            "errors": [],
        })

        response = await test_client.post(
            "/messages/batch/generate",
            json={
                "campaign_id": 1,
                "prospect_ids": [1, 2, 3],
                "message_types": ["email_initial"],
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["prospects_processed"] == 3


class TestMessageRoutesErrorHandling:
    """Tests for error handling in message routes."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.messages.get_message_service") as mock_ms:
            mock_service = MagicMock()
            mock_ms.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.mark.asyncio
    async def test_generate_server_error(self, client):
        """Test server error during message generation."""
        test_client, mock_service = client
        mock_service.generate_messages = AsyncMock(
            side_effect=Exception("AI service error")
        )

        response = await test_client.post(
            "/messages/generate",
            json={
                "campaign_id": 1,
                "message_types": ["email_initial"],
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_approve_empty_list(self, client):
        """Test approving empty message list."""
        test_client, mock_service = client

        response = await test_client.post(
            "/messages/approve",
            json={"message_ids": []},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 422  # Validation error
