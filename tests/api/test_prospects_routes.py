"""
API tests for prospect routes.

Tests cover:
- CRUD operations
- CSV/JSON import
- Bulk operations
- Brand brief linking
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class TestProspectRoutes:
    """Tests for prospect API endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.prospects.get_prospect_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service_factory.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.fixture
    def sample_prospect_response(self):
        """Sample prospect response data."""
        return {
            "id": 1,
            "campaign_id": 1,
            "full_name": "John Doe",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "linkedin_url": "https://linkedin.com/in/johndoe",
            "company": "Acme Corp",
            "title": "VP Marketing",
            "industry": "Technology",
            "location": "San Francisco",
            "status": "new",
            "engagement_score": 0.0,
            "personalization_score": None,
            "message_count": 0,
            "last_contacted_at": None,
            "created_at": "2024-01-01T00:00:00",
        }

    @pytest.mark.asyncio
    async def test_create_prospect(self, client, sample_prospect_response):
        """Test creating a new prospect."""
        test_client, mock_service = client
        mock_service.create_prospect = AsyncMock(return_value=sample_prospect_response)

        response = await test_client.post(
            "/prospects",
            json={
                "campaign_id": 1,
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "company": "Acme Corp",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "John"
        assert data["email"] == "john@example.com"

    @pytest.mark.asyncio
    async def test_create_prospect_minimal(self, client, sample_prospect_response):
        """Test creating prospect with minimal fields."""
        test_client, mock_service = client
        mock_service.create_prospect = AsyncMock(return_value=sample_prospect_response)

        response = await test_client.post(
            "/prospects",
            json={
                "campaign_id": 1,
                "first_name": "John",
                "last_name": "Doe",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_list_prospects(self, client, sample_prospect_response):
        """Test listing prospects."""
        test_client, mock_service = client
        mock_service.list_prospects = AsyncMock(return_value={
            "items": [sample_prospect_response],
            "total": 1,
        })

        response = await test_client.get("/prospects")

        assert response.status_code == 200
        data = response.json()
        assert len(data["prospects"]) == 1
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_prospects_with_filters(self, client, sample_prospect_response):
        """Test listing prospects with filters."""
        test_client, mock_service = client
        mock_service.list_prospects = AsyncMock(return_value={
            "items": [sample_prospect_response],
            "total": 1,
        })

        response = await test_client.get(
            "/prospects?campaign_id=1&status=new&company=Acme"
        )

        assert response.status_code == 200
        call_kwargs = mock_service.list_prospects.call_args[1]
        assert call_kwargs["campaign_id"] == 1
        assert call_kwargs["status"] == "new"
        assert call_kwargs["company"] == "Acme"

    @pytest.mark.asyncio
    async def test_list_prospects_with_search(self, client, sample_prospect_response):
        """Test listing prospects with search."""
        test_client, mock_service = client
        mock_service.list_prospects = AsyncMock(return_value={
            "items": [sample_prospect_response],
            "total": 1,
        })

        response = await test_client.get("/prospects?search=john")

        assert response.status_code == 200
        call_kwargs = mock_service.list_prospects.call_args[1]
        assert call_kwargs["search"] == "john"

    @pytest.mark.asyncio
    async def test_get_prospect(self, client, sample_prospect_response):
        """Test getting a single prospect."""
        test_client, mock_service = client
        mock_service.get_prospect = AsyncMock(return_value=sample_prospect_response)

        response = await test_client.get("/prospects/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["first_name"] == "John"

    @pytest.mark.asyncio
    async def test_get_prospect_not_found(self, client):
        """Test getting non-existent prospect."""
        test_client, mock_service = client
        mock_service.get_prospect = AsyncMock(return_value=None)

        response = await test_client.get("/prospects/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_prospect(self, client, sample_prospect_response):
        """Test updating a prospect."""
        test_client, mock_service = client
        updated = {**sample_prospect_response, "title": "CEO"}
        mock_service.update_prospect = AsyncMock(return_value=updated)

        response = await test_client.patch(
            "/prospects/1",
            json={"title": "CEO"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "CEO"

    @pytest.mark.asyncio
    async def test_update_prospect_status(self, client, sample_prospect_response):
        """Test updating prospect status."""
        test_client, mock_service = client
        updated = {**sample_prospect_response, "status": "contacted"}
        mock_service.update_prospect = AsyncMock(return_value=updated)

        response = await test_client.patch(
            "/prospects/1",
            json={"status": "contacted"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "contacted"

    @pytest.mark.asyncio
    async def test_update_prospect_not_found(self, client):
        """Test updating non-existent prospect."""
        test_client, mock_service = client
        mock_service.update_prospect = AsyncMock(return_value=None)

        response = await test_client.patch(
            "/prospects/999",
            json={"title": "CEO"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_prospect_no_fields(self, client):
        """Test updating prospect with no fields."""
        test_client, mock_service = client

        response = await test_client.patch(
            "/prospects/1",
            json={},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 400
        assert "No update fields" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_prospect(self, client):
        """Test deleting a prospect."""
        test_client, mock_service = client
        mock_service.delete_prospect = AsyncMock(return_value=True)

        response = await test_client.delete(
            "/prospects/1",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_prospect_not_found(self, client):
        """Test deleting non-existent prospect."""
        test_client, mock_service = client
        mock_service.delete_prospect = AsyncMock(return_value=False)

        response = await test_client.delete(
            "/prospects/999",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_prospect_messages(self, client):
        """Test getting prospect messages."""
        test_client, mock_service = client
        mock_service.get_prospect_messages = AsyncMock(return_value={
            "messages": [
                {
                    "id": 1,
                    "channel": "email",
                    "subject": "Test",
                    "status": "sent",
                }
            ],
            "total": 1,
        })

        response = await test_client.get("/prospects/1/messages")

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1

    @pytest.mark.asyncio
    async def test_get_prospect_messages_not_found(self, client):
        """Test getting messages for non-existent prospect."""
        test_client, mock_service = client
        mock_service.get_prospect_messages = AsyncMock(return_value=None)

        response = await test_client.get("/prospects/999/messages")

        assert response.status_code == 404


class TestProspectImport:
    """Tests for prospect import endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.prospects.get_prospect_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service_factory.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.mark.asyncio
    async def test_import_csv(self, client):
        """Test CSV import."""
        test_client, mock_service = client
        mock_service.import_from_csv = AsyncMock(return_value={
            "imported": 3,
            "skipped": 0,
            "errors": 0,
            "error_details": [],
        })

        csv_content = b"first_name,last_name,email\nJohn,Doe,john@example.com"

        response = await test_client.post(
            "/prospects/import/csv",
            data={"campaign_id": "1"},
            files={"file": ("prospects.csv", csv_content, "text/csv")},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 3

    @pytest.mark.asyncio
    async def test_import_csv_invalid_file_type(self, client):
        """Test CSV import with invalid file type."""
        test_client, mock_service = client

        response = await test_client.post(
            "/prospects/import/csv",
            data={"campaign_id": "1"},
            files={"file": ("prospects.txt", b"content", "text/plain")},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 400
        assert "CSV file" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_import_json(self, client):
        """Test JSON import."""
        test_client, mock_service = client
        mock_service.import_from_json = AsyncMock(return_value={
            "imported": 2,
            "skipped": 0,
            "errors": 0,
            "error_details": [],
        })

        json_content = b'[{"first_name": "John", "last_name": "Doe"}]'

        response = await test_client.post(
            "/prospects/import/json",
            data={"campaign_id": "1"},
            files={"file": ("prospects.json", json_content, "application/json")},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 2

    @pytest.mark.asyncio
    async def test_import_json_invalid_format(self, client):
        """Test JSON import with invalid JSON."""
        test_client, mock_service = client

        response = await test_client.post(
            "/prospects/import/json",
            data={"campaign_id": "1"},
            files={"file": ("prospects.json", b"invalid json", "application/json")},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_import_json_not_array(self, client):
        """Test JSON import with non-array JSON."""
        test_client, mock_service = client

        response = await test_client.post(
            "/prospects/import/json",
            data={"campaign_id": "1"},
            files={"file": ("prospects.json", b'{"name": "John"}', "application/json")},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 400
        assert "array" in response.json()["detail"].lower()


class TestProspectBulkOperations:
    """Tests for bulk prospect operations."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.prospects.get_prospect_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service_factory.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.mark.asyncio
    async def test_bulk_update_status(self, client):
        """Test bulk status update."""
        test_client, mock_service = client
        mock_service.bulk_update_status = AsyncMock(return_value={
            "updated": 3,
            "not_found": 0,
        })

        response = await test_client.post(
            "/prospects/bulk/update-status",
            json={
                "prospect_ids": [1, 2, 3],
                "status": "opted_out",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["updated"] == 3


class TestProspectBrandBriefLinking:
    """Tests for brand brief linking."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.prospects.get_prospect_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service_factory.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.fixture
    def sample_prospect_response(self):
        """Sample prospect response data."""
        return {
            "id": 1,
            "campaign_id": 1,
            "full_name": "John Doe",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "linkedin_url": None,
            "company": "Acme Corp",
            "title": None,
            "industry": None,
            "location": None,
            "status": "new",
            "engagement_score": 0.0,
            "personalization_score": None,
            "message_count": 0,
            "last_contacted_at": None,
            "created_at": "2024-01-01T00:00:00",
            "brand_brief_path": "/briefs/acme.md",
        }

    @pytest.mark.asyncio
    async def test_link_brand_brief(self, client, sample_prospect_response):
        """Test linking brand brief to prospect."""
        test_client, mock_service = client
        mock_service.link_brand_brief = AsyncMock(return_value=sample_prospect_response)

        response = await test_client.post(
            "/prospects/1/link-brief",
            data={"brand_brief_path": "/briefs/acme.md"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "brand_brief_path" in data

    @pytest.mark.asyncio
    async def test_link_brand_brief_not_found(self, client):
        """Test linking brand brief to non-existent prospect."""
        test_client, mock_service = client
        mock_service.link_brand_brief = AsyncMock(return_value=None)

        response = await test_client.post(
            "/prospects/999/link-brief",
            data={"brand_brief_path": "/briefs/acme.md"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_link_brand_brief_file_not_found(self, client):
        """Test linking non-existent brand brief."""
        test_client, mock_service = client
        mock_service.link_brand_brief = AsyncMock(side_effect=FileNotFoundError())

        response = await test_client.post(
            "/prospects/1/link-brief",
            data={"brand_brief_path": "/briefs/nonexistent.md"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()


class TestProspectRoutesErrorHandling:
    """Tests for error handling in prospect routes."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.prospects.get_prospect_service") as mock_service_factory:
            mock_service = MagicMock()
            mock_service_factory.return_value = mock_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_service

    @pytest.mark.asyncio
    async def test_create_prospect_server_error(self, client):
        """Test server error during prospect creation."""
        test_client, mock_service = client
        mock_service.create_prospect = AsyncMock(side_effect=Exception("Database error"))

        response = await test_client.post(
            "/prospects",
            json={
                "campaign_id": 1,
                "first_name": "John",
                "last_name": "Doe",
            },
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 500
        assert "Failed to create" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_prospects_server_error(self, client):
        """Test server error during prospect listing."""
        test_client, mock_service = client
        mock_service.list_prospects = AsyncMock(side_effect=Exception("Database error"))

        response = await test_client.get("/prospects")

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_import_csv_encoding_error(self, client):
        """Test CSV import with encoding error."""
        test_client, mock_service = client

        # Invalid UTF-8 bytes
        invalid_content = b"\xff\xfe invalid encoding"

        response = await test_client.post(
            "/prospects/import/csv",
            data={"campaign_id": "1"},
            files={"file": ("prospects.csv", invalid_content, "text/csv")},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 400
        assert "encoding" in response.json()["detail"].lower()
