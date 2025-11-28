"""
API tests for project routes.

Tests cover:
- Project CRUD operations
- Project listing
- Project status
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class TestProjectRoutes:
    """Tests for project API endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.projects.get_file_service") as mock_fs:
            mock_file_service = MagicMock()
            mock_fs.return_value = mock_file_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_file_service

    @pytest.fixture
    def sample_project(self):
        """Sample project data."""
        return {
            "id": "test-project-2024",
            "name": "Test Campaign Project",
            "country": "Paraguay",
            "language": "es",
            "brand": "Test Brand",
            "type": "digital",
        }

    @pytest.mark.asyncio
    async def test_create_project(self, client, sample_project):
        """Test creating a new project."""
        test_client, mock_fs = client
        mock_fs.create_project_structure = MagicMock()
        mock_fs.get_project_path = MagicMock(return_value="/projects/test-project")

        response = await test_client.post(
            "/projects",
            json=sample_project,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_project["id"]

    @pytest.mark.asyncio
    async def test_create_project_already_exists(self, client, sample_project):
        """Test creating project that already exists."""
        test_client, mock_fs = client
        mock_fs.create_project_structure.side_effect = FileExistsError("Project exists")

        response = await test_client.post(
            "/projects",
            json=sample_project,
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_list_projects(self, client):
        """Test listing all projects."""
        test_client, mock_fs = client
        mock_fs.list_projects = MagicMock(return_value=[
            "project-1",
            "project-2",
            "project-3",
        ])
        mock_fs.get_project_metadata = MagicMock(return_value={
            "name": "Project Name",
            "status": "created",
        })

        response = await test_client.get("/projects")

        assert response.status_code == 200
        data = response.json()
        assert len(data["projects"]) == 3

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, client):
        """Test listing projects when none exist."""
        test_client, mock_fs = client
        mock_fs.list_projects = MagicMock(return_value=[])

        response = await test_client.get("/projects")

        assert response.status_code == 200
        data = response.json()
        assert data["projects"] == []

    @pytest.mark.asyncio
    async def test_get_project(self, client):
        """Test getting a specific project."""
        test_client, mock_fs = client
        mock_fs.get_project_metadata = MagicMock(return_value={
            "name": "Test Project",
            "country": "Paraguay",
            "status": "ideas_generated",
            "ideas_count": 25,
        })
        mock_fs.get_project_path = MagicMock(return_value="/projects/test-project")

        response = await test_client.get("/projects/test-project")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["ideas_count"] == 25

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, client):
        """Test getting non-existent project."""
        test_client, mock_fs = client
        mock_fs.get_project_metadata = MagicMock(return_value=None)

        response = await test_client.get("/projects/nonexistent")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(self, client):
        """Test deleting a project."""
        test_client, mock_fs = client
        mock_fs.delete_project = MagicMock()

        response = await test_client.delete("/projects/test-project")

        assert response.status_code == 200
        mock_fs.delete_project.assert_called_once_with("test-project")

    @pytest.mark.asyncio
    async def test_delete_project_not_found(self, client):
        """Test deleting non-existent project."""
        test_client, mock_fs = client
        mock_fs.delete_project.side_effect = FileNotFoundError("Not found")

        response = await test_client.delete("/projects/nonexistent")

        assert response.status_code == 404


class TestProjectStatusRoutes:
    """Tests for project status endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.projects.get_file_service") as mock_fs:
            mock_file_service = MagicMock()
            mock_fs.return_value = mock_file_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_file_service

    @pytest.mark.asyncio
    async def test_get_project_status(self, client):
        """Test getting project status."""
        test_client, mock_fs = client
        mock_fs.get_project_metadata = MagicMock(return_value={
            "status": "ideas_generated",
            "ideas_count": 25,
            "top_score": 8.5,
        })

        response = await test_client.get("/projects/test-project/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ideas_generated"

    @pytest.mark.asyncio
    async def test_update_project_status(self, client):
        """Test updating project status."""
        test_client, mock_fs = client
        mock_fs.update_project_metadata = MagicMock()

        response = await test_client.patch(
            "/projects/test-project/status",
            json={"status": "in_review"},
        )

        assert response.status_code == 200
        mock_fs.update_project_metadata.assert_called_once()


class TestProjectFilesRoutes:
    """Tests for project files endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.projects.get_file_service") as mock_fs:
            mock_file_service = MagicMock()
            mock_fs.return_value = mock_file_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_file_service

    @pytest.mark.asyncio
    async def test_list_project_files(self, client):
        """Test listing project files."""
        test_client, mock_fs = client
        mock_fs.get_idea_files = MagicMock(return_value=[
            "ideas/idea-001.md",
            "ideas/idea-002.md",
        ])
        mock_fs.get_research_files = MagicMock(return_value=[
            "research/01-mercado/analysis.md",
        ])

        response = await test_client.get("/projects/test-project/files")

        assert response.status_code == 200
        data = response.json()
        assert "ideas" in data
        assert "research" in data

    @pytest.mark.asyncio
    async def test_get_project_file(self, client):
        """Test getting a specific project file."""
        test_client, mock_fs = client
        mock_fs.read_file = AsyncMock(return_value="# File Content\n\nText here.")

        response = await test_client.get(
            "/projects/test-project/files/brief.md"
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_project_file_not_found(self, client):
        """Test getting non-existent file."""
        test_client, mock_fs = client
        mock_fs.read_file = AsyncMock(side_effect=FileNotFoundError())

        response = await test_client.get(
            "/projects/test-project/files/nonexistent.md"
        )

        assert response.status_code == 404


class TestProjectValidation:
    """Tests for project validation."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client."""
        with patch("api.routes.projects.get_file_service"):
            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client

    @pytest.mark.asyncio
    async def test_create_project_missing_id(self, client):
        """Test creating project without ID."""
        response = await client.post(
            "/projects",
            json={
                "name": "Test Project",
                # Missing id
            },
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_project_invalid_country(self, client):
        """Test creating project with invalid country."""
        response = await client.post(
            "/projects",
            json={
                "id": "test-project",
                "name": "Test",
                "country": "",  # Empty country
            },
        )

        # Should either reject or accept with default
        assert response.status_code in [200, 422]


class TestProjectRoutesErrorHandling:
    """Tests for error handling in project routes."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.projects.get_file_service") as mock_fs:
            mock_file_service = MagicMock()
            mock_fs.return_value = mock_file_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_file_service

    @pytest.mark.asyncio
    async def test_create_project_server_error(self, client):
        """Test server error during project creation."""
        test_client, mock_fs = client
        mock_fs.create_project_structure.side_effect = Exception("Disk error")

        response = await test_client.post(
            "/projects",
            json={
                "id": "test-project",
                "name": "Test",
            },
        )

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_list_projects_server_error(self, client):
        """Test server error during project listing."""
        test_client, mock_fs = client
        mock_fs.list_projects.side_effect = Exception("IO error")

        response = await test_client.get("/projects")

        assert response.status_code == 500
