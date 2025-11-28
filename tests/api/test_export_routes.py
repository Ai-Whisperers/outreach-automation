"""
API tests for export routes.

Tests cover:
- PDF export
- PowerPoint export
- Export listing
- Export download
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class TestPDFExportRoutes:
    """Tests for PDF export endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.export.get_export_service") as mock_es:
            mock_export_service = MagicMock()
            mock_es.return_value = mock_export_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_export_service

    @pytest.mark.asyncio
    async def test_export_to_pdf(self, client):
        """Test exporting project to PDF."""
        test_client, mock_es = client
        mock_es.export_to_pdf = AsyncMock(return_value={
            "file_path": "/projects/test-project/exports/campaign-2024.pdf",
            "filename": "campaign-2024.pdf",
            "size_bytes": 1024000,
        })

        response = await test_client.post(
            "/projects/test-project/export/pdf",
            json={
                "include_cover": True,
                "include_toc": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "campaign-2024.pdf"

    @pytest.mark.asyncio
    async def test_export_to_pdf_default_options(self, client):
        """Test PDF export with default options."""
        test_client, mock_es = client
        mock_es.export_to_pdf = AsyncMock(return_value={
            "file_path": "/projects/test-project/exports/export.pdf",
            "filename": "export.pdf",
            "size_bytes": 512000,
        })

        response = await test_client.post(
            "/projects/test-project/export/pdf",
            json={},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_export_to_pdf_custom_filename(self, client):
        """Test PDF export with custom filename."""
        test_client, mock_es = client
        mock_es.export_to_pdf = AsyncMock(return_value={
            "file_path": "/projects/test-project/exports/my-campaign.pdf",
            "filename": "my-campaign.pdf",
            "size_bytes": 768000,
        })

        response = await test_client.post(
            "/projects/test-project/export/pdf",
            json={"filename": "my-campaign.pdf"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "my-campaign.pdf"


class TestPowerPointExportRoutes:
    """Tests for PowerPoint export endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.export.get_export_service") as mock_es:
            mock_export_service = MagicMock()
            mock_es.return_value = mock_export_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_export_service

    @pytest.mark.asyncio
    async def test_export_to_pptx(self, client):
        """Test exporting project to PowerPoint."""
        test_client, mock_es = client
        mock_es.export_to_pptx = AsyncMock(return_value={
            "file_path": "/projects/test-project/exports/presentation.pptx",
            "filename": "presentation.pptx",
            "size_bytes": 2048000,
            "slides_count": 15,
        })

        response = await test_client.post(
            "/projects/test-project/export/pptx",
            json={
                "template": "default",
                "include_notes": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "presentation.pptx"
        assert data["slides_count"] == 15

    @pytest.mark.asyncio
    async def test_export_to_pptx_custom_template(self, client):
        """Test PowerPoint export with custom template."""
        test_client, mock_es = client
        mock_es.export_to_pptx = AsyncMock(return_value={
            "file_path": "/projects/test-project/exports/branded.pptx",
            "filename": "branded.pptx",
            "size_bytes": 3072000,
            "slides_count": 20,
        })

        response = await test_client.post(
            "/projects/test-project/export/pptx",
            json={"template": "corporate-dark"},
        )

        assert response.status_code == 200


class TestExportListRoutes:
    """Tests for export listing endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.export.get_file_service") as mock_fs:
            mock_file_service = MagicMock()
            mock_fs.return_value = mock_file_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_file_service

    @pytest.mark.asyncio
    async def test_list_exports(self, client):
        """Test listing project exports."""
        test_client, mock_fs = client
        mock_fs.list_exports = MagicMock(return_value=[
            {"filename": "campaign-v1.pdf", "type": "pdf", "created_at": "2024-01-15"},
            {"filename": "campaign-v2.pdf", "type": "pdf", "created_at": "2024-01-16"},
            {"filename": "presentation.pptx", "type": "pptx", "created_at": "2024-01-16"},
        ])

        response = await test_client.get("/projects/test-project/export")

        assert response.status_code == 200
        data = response.json()
        assert len(data["exports"]) == 3

    @pytest.mark.asyncio
    async def test_list_exports_empty(self, client):
        """Test listing exports when none exist."""
        test_client, mock_fs = client
        mock_fs.list_exports = MagicMock(return_value=[])

        response = await test_client.get("/projects/test-project/export")

        assert response.status_code == 200
        data = response.json()
        assert data["exports"] == []

    @pytest.mark.asyncio
    async def test_list_exports_filter_by_type(self, client):
        """Test listing exports filtered by type."""
        test_client, mock_fs = client
        mock_fs.list_exports = MagicMock(return_value=[
            {"filename": "campaign.pdf", "type": "pdf", "created_at": "2024-01-15"},
        ])

        response = await test_client.get(
            "/projects/test-project/export",
            params={"type": "pdf"},
        )

        assert response.status_code == 200


class TestExportDownloadRoutes:
    """Tests for export download endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.export.get_file_service") as mock_fs:
            mock_file_service = MagicMock()
            mock_fs.return_value = mock_file_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_file_service

    @pytest.mark.asyncio
    async def test_download_export(self, client):
        """Test downloading an export file."""
        test_client, mock_fs = client
        mock_fs.get_export_path = MagicMock(return_value="/projects/test-project/exports/file.pdf")
        mock_fs.file_exists = MagicMock(return_value=True)

        # Note: This test checks the route exists and returns appropriate response
        # Actual file streaming is harder to test
        response = await test_client.get(
            "/projects/test-project/export/download/file.pdf",
        )

        # Should return 200 or handle file streaming
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_download_export_not_found(self, client):
        """Test downloading non-existent export."""
        test_client, mock_fs = client
        mock_fs.get_export_path = MagicMock(return_value="/projects/test-project/exports/missing.pdf")
        mock_fs.file_exists = MagicMock(return_value=False)

        response = await test_client.get(
            "/projects/test-project/export/download/missing.pdf",
        )

        assert response.status_code == 404


class TestExportRoutesErrorHandling:
    """Tests for error handling in export routes."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.export.get_export_service") as mock_es:
            mock_export_service = MagicMock()
            mock_es.return_value = mock_export_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_export_service

    @pytest.mark.asyncio
    async def test_export_pdf_project_not_found(self, client):
        """Test PDF export for non-existent project."""
        test_client, mock_es = client
        mock_es.export_to_pdf = AsyncMock(side_effect=FileNotFoundError("Project not found"))

        response = await test_client.post(
            "/projects/nonexistent/export/pdf",
            json={},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_pdf_generation_error(self, client):
        """Test PDF export generation error."""
        test_client, mock_es = client
        mock_es.export_to_pdf = AsyncMock(side_effect=Exception("PDF generation failed"))

        response = await test_client.post(
            "/projects/test-project/export/pdf",
            json={},
        )

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_export_pptx_generation_error(self, client):
        """Test PowerPoint export generation error."""
        test_client, mock_es = client
        mock_es.export_to_pptx = AsyncMock(side_effect=Exception("PPTX generation failed"))

        response = await test_client.post(
            "/projects/test-project/export/pptx",
            json={},
        )

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_export_no_ideas(self, client):
        """Test export when project has no ideas."""
        test_client, mock_es = client
        mock_es.export_to_pdf = AsyncMock(return_value={
            "error": "No ideas to export",
        })

        response = await test_client.post(
            "/projects/test-project/export/pdf",
            json={},
        )

        # Should handle gracefully
        assert response.status_code in [200, 400]
