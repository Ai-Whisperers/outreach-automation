"""
API tests for research routes.

Tests cover:
- Research listing
- Adding research
- Auto research
- Research synthesis
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class TestResearchListRoutes:
    """Tests for research listing endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.research.get_file_service") as mock_fs:
            with patch("api.routes.research.get_research_service") as mock_rs:
                mock_file_service = MagicMock()
                mock_research_service = MagicMock()
                mock_fs.return_value = mock_file_service
                mock_rs.return_value = mock_research_service

                from api.main import app

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    yield client, mock_file_service, mock_research_service

    @pytest.mark.asyncio
    async def test_list_research(self, client):
        """Test listing research files."""
        test_client, mock_fs, mock_rs = client
        mock_fs.get_research_files = MagicMock(return_value=[
            "research/01-mercado/analysis.md",
            "research/02-consumidor/personas.md",
        ])

        response = await test_client.get("/projects/test-project/research")

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 2

    @pytest.mark.asyncio
    async def test_list_research_by_category(self, client):
        """Test listing research by category."""
        test_client, mock_fs, mock_rs = client
        mock_fs.get_research_files = MagicMock(return_value=[
            "research/01-mercado/analysis.md",
            "research/01-mercado/competitors.md",
        ])

        response = await test_client.get(
            "/projects/test-project/research",
            params={"category": "01-mercado"},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_research_empty(self, client):
        """Test listing research when none exists."""
        test_client, mock_fs, mock_rs = client
        mock_fs.get_research_files = MagicMock(return_value=[])

        response = await test_client.get("/projects/test-project/research")

        assert response.status_code == 200
        data = response.json()
        assert data["files"] == []


class TestResearchAddRoutes:
    """Tests for adding research endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.research.get_file_service") as mock_fs:
            with patch("api.routes.research.get_research_service") as mock_rs:
                mock_file_service = MagicMock()
                mock_research_service = MagicMock()
                mock_fs.return_value = mock_file_service
                mock_rs.return_value = mock_research_service

                from api.main import app

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    yield client, mock_file_service, mock_research_service

    @pytest.mark.asyncio
    async def test_add_research_sources(self, client):
        """Test adding research sources."""
        test_client, mock_fs, mock_rs = client
        mock_rs.add_research = AsyncMock(return_value={
            "sources_added": 3,
            "files_created": ["source-1.md", "source-2.md", "source-3.md"],
        })

        response = await test_client.post(
            "/projects/test-project/research",
            json={
                "sources": [
                    {"url": "https://example.com/article1", "category": "01-mercado"},
                    {"url": "https://example.com/article2", "category": "01-mercado"},
                    {"url": "https://example.com/article3", "category": "02-consumidor"},
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sources_added"] == 3

    @pytest.mark.asyncio
    async def test_add_research_manual(self, client):
        """Test adding manual research content."""
        test_client, mock_fs, mock_rs = client
        mock_fs.save_research_file = AsyncMock()

        response = await test_client.post(
            "/projects/test-project/research/manual",
            json={
                "category": "01-mercado",
                "filename": "manual-research.md",
                "content": "# Manual Research\n\nContent here.",
            },
        )

        assert response.status_code == 200
        mock_fs.save_research_file.assert_called_once()


class TestAutoResearchRoutes:
    """Tests for auto research endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.research.get_research_automation") as mock_ra:
            mock_automation = MagicMock()
            mock_ra.return_value = mock_automation

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_automation

    @pytest.mark.asyncio
    async def test_auto_research(self, client):
        """Test automated research."""
        test_client, mock_ra = client
        mock_ra.run_full_research = AsyncMock(return_value={
            "queries_generated": 10,
            "sources_found": 25,
            "sources_processed": 20,
            "files_created": 20,
        })

        response = await test_client.post(
            "/projects/test-project/research/auto",
            json={
                "categories": ["01-mercado", "02-consumidor"],
                "max_sources_per_category": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["queries_generated"] == 10

    @pytest.mark.asyncio
    async def test_auto_research_default_categories(self, client):
        """Test auto research with default categories."""
        test_client, mock_ra = client
        mock_ra.run_full_research = AsyncMock(return_value={
            "queries_generated": 5,
            "sources_found": 10,
            "sources_processed": 8,
            "files_created": 8,
        })

        response = await test_client.post(
            "/projects/test-project/research/auto",
            json={},  # Use defaults
        )

        assert response.status_code == 200


class TestResearchSynthesisRoutes:
    """Tests for research synthesis endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.research.get_research_service") as mock_rs:
            mock_research_service = MagicMock()
            mock_rs.return_value = mock_research_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_research_service

    @pytest.mark.asyncio
    async def test_synthesize_research(self, client):
        """Test research synthesis."""
        test_client, mock_rs = client
        mock_rs.synthesize = AsyncMock(return_value={
            "summary": "Research synthesis summary",
            "key_insights": ["Insight 1", "Insight 2"],
            "file_path": "quick-reference.md",
        })

        response = await test_client.post(
            "/projects/test-project/research/synthesize",
        )

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data

    @pytest.mark.asyncio
    async def test_get_research_summary(self, client):
        """Test getting research summary."""
        test_client, mock_rs = client
        mock_rs.get_all_research = AsyncMock(return_value="# Research Summary\n\nAll research content.")

        response = await test_client.get(
            "/projects/test-project/research/summary",
        )

        assert response.status_code == 200


class TestResearchFileRoutes:
    """Tests for individual research file operations."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.research.get_file_service") as mock_fs:
            mock_file_service = MagicMock()
            mock_fs.return_value = mock_file_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_file_service

    @pytest.mark.asyncio
    async def test_get_research_file(self, client):
        """Test getting a specific research file."""
        test_client, mock_fs = client
        mock_fs.read_file = AsyncMock(return_value="# Research Content\n\nDetails here.")

        response = await test_client.get(
            "/projects/test-project/research/01-mercado/analysis.md",
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_research_file_not_found(self, client):
        """Test getting non-existent research file."""
        test_client, mock_fs = client
        mock_fs.read_file = AsyncMock(side_effect=FileNotFoundError())

        response = await test_client.get(
            "/projects/test-project/research/01-mercado/nonexistent.md",
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_research_file(self, client):
        """Test deleting a research file."""
        test_client, mock_fs = client
        mock_fs.delete_file = MagicMock()

        response = await test_client.delete(
            "/projects/test-project/research/01-mercado/old-research.md",
        )

        assert response.status_code == 200


class TestResearchRoutesErrorHandling:
    """Tests for error handling in research routes."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.research.get_research_service") as mock_rs:
            with patch("api.routes.research.get_research_automation") as mock_ra:
                mock_research_service = MagicMock()
                mock_automation = MagicMock()
                mock_rs.return_value = mock_research_service
                mock_ra.return_value = mock_automation

                from api.main import app

                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    yield client, mock_research_service, mock_automation

    @pytest.mark.asyncio
    async def test_add_research_server_error(self, client):
        """Test server error during research addition."""
        test_client, mock_rs, mock_ra = client
        mock_rs.add_research = AsyncMock(side_effect=Exception("Network error"))

        response = await test_client.post(
            "/projects/test-project/research",
            json={
                "sources": [{"url": "https://example.com", "category": "01-mercado"}],
            },
        )

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_auto_research_server_error(self, client):
        """Test server error during auto research."""
        test_client, mock_rs, mock_ra = client
        mock_ra.run_full_research = AsyncMock(side_effect=Exception("AI error"))

        response = await test_client.post(
            "/projects/test-project/research/auto",
            json={},
        )

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_synthesize_research_server_error(self, client):
        """Test server error during synthesis."""
        test_client, mock_rs, mock_ra = client
        mock_rs.synthesize = AsyncMock(side_effect=Exception("Synthesis failed"))

        response = await test_client.post(
            "/projects/test-project/research/synthesize",
        )

        assert response.status_code == 500
