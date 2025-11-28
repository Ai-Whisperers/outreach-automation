"""
Service tests for file operations module.

Tests cover:
- Project structure creation
- File reading and writing
- Project metadata management
- Idea file operations
- Research file operations
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestFileServiceInitialization:
    """Tests for FileOperationsService initialization."""

    def test_service_initialization(self, tmp_path):
        """Test service initializes correctly."""
        with patch("api.services.file_operations.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            from api.services.file_operations import FileOperationsService

            service = FileOperationsService()

            assert service.projects_dir == tmp_path


class TestProjectStructure:
    """Tests for project structure operations."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create file service with temp directory."""
        with patch("api.services.file_operations.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            from api.services.file_operations import FileOperationsService

            return FileOperationsService()

    def test_create_project_structure(self, service, tmp_path):
        """Test creating project directory structure."""
        project_id = "test-project"

        service.create_project_structure(project_id)

        project_dir = tmp_path / project_id
        assert project_dir.exists()
        assert (project_dir / "research").exists()
        assert (project_dir / "ideas").exists()

    def test_create_project_structure_with_metadata(self, service, tmp_path):
        """Test creating project with metadata."""
        project_id = "test-project"
        metadata = {
            "name": "Test Project",
            "country": "Paraguay",
            "language": "es",
        }

        service.create_project_structure(project_id, metadata=metadata)

        metadata_file = tmp_path / project_id / "metadata.json"
        assert metadata_file.exists()

        with open(metadata_file) as f:
            saved_metadata = json.load(f)

        assert saved_metadata["name"] == "Test Project"
        assert saved_metadata["country"] == "Paraguay"

    def test_get_project_path(self, service, tmp_path):
        """Test getting project path."""
        project_id = "my-project"

        path = service.get_project_path(project_id)

        assert path == tmp_path / project_id

    def test_list_projects(self, service, tmp_path):
        """Test listing projects."""
        # Create some projects
        (tmp_path / "project-1").mkdir()
        (tmp_path / "project-2").mkdir()
        (tmp_path / "not-a-project.txt").write_text("file")

        projects = service.list_projects()

        assert "project-1" in projects
        assert "project-2" in projects
        assert "not-a-project.txt" not in projects

    def test_delete_project(self, service, tmp_path):
        """Test deleting a project."""
        project_id = "to-delete"
        project_dir = tmp_path / project_id
        project_dir.mkdir()
        (project_dir / "file.txt").write_text("content")

        service.delete_project(project_id)

        assert not project_dir.exists()


class TestFileOperations:
    """Tests for basic file operations."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create file service with temp directory."""
        with patch("api.services.file_operations.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            from api.services.file_operations import FileOperationsService

            service = FileOperationsService()
            # Create a test project
            (tmp_path / "test-project").mkdir()
            return service

    @pytest.mark.asyncio
    async def test_write_file(self, service, tmp_path):
        """Test writing a file."""
        project_id = "test-project"
        content = "# Test Content\n\nSome text here."

        await service.write_file(project_id, "test.md", content)

        file_path = tmp_path / project_id / "test.md"
        assert file_path.exists()
        assert file_path.read_text() == content

    @pytest.mark.asyncio
    async def test_read_file(self, service, tmp_path):
        """Test reading a file."""
        project_id = "test-project"
        file_path = tmp_path / project_id / "existing.md"
        file_path.write_text("File content")

        content = await service.read_file(project_id, "existing.md")

        assert content == "File content"

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, service):
        """Test reading non-existent file."""
        with pytest.raises(Exception):
            await service.read_file("test-project", "nonexistent.md")

    @pytest.mark.asyncio
    async def test_write_file_creates_subdirs(self, service, tmp_path):
        """Test writing file creates subdirectories."""
        project_id = "test-project"

        await service.write_file(project_id, "subdir/nested/file.md", "content")

        file_path = tmp_path / project_id / "subdir" / "nested" / "file.md"
        assert file_path.exists()


class TestMetadataOperations:
    """Tests for project metadata operations."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create file service with temp directory."""
        with patch("api.services.file_operations.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            from api.services.file_operations import FileOperationsService

            service = FileOperationsService()
            # Create a test project with metadata
            project_dir = tmp_path / "test-project"
            project_dir.mkdir()
            metadata = {"name": "Test", "status": "created"}
            (project_dir / "metadata.json").write_text(json.dumps(metadata))
            return service

    def test_get_project_metadata(self, service):
        """Test getting project metadata."""
        metadata = service.get_project_metadata("test-project")

        assert metadata["name"] == "Test"
        assert metadata["status"] == "created"

    def test_get_project_metadata_missing(self, service, tmp_path):
        """Test getting metadata from project without metadata file."""
        (tmp_path / "no-metadata").mkdir()

        metadata = service.get_project_metadata("no-metadata")

        assert metadata == {}

    def test_update_project_metadata(self, service, tmp_path):
        """Test updating project metadata."""
        service.update_project_metadata("test-project", {
            "status": "in_progress",
            "ideas_count": 5,
        })

        metadata_file = tmp_path / "test-project" / "metadata.json"
        with open(metadata_file) as f:
            metadata = json.load(f)

        assert metadata["status"] == "in_progress"
        assert metadata["ideas_count"] == 5
        assert metadata["name"] == "Test"  # Original value preserved


class TestIdeaOperations:
    """Tests for idea file operations."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create file service with temp directory."""
        with patch("api.services.file_operations.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            from api.services.file_operations import FileOperationsService

            service = FileOperationsService()
            # Create project with ideas directory
            project_dir = tmp_path / "test-project"
            (project_dir / "ideas").mkdir(parents=True)
            return service

    @pytest.mark.asyncio
    async def test_save_idea(self, service, tmp_path):
        """Test saving an idea."""
        project_id = "test-project"
        idea_number = 1
        content = "# Idea 1\n\nDescription here."

        file_path = await service.save_idea(project_id, idea_number, content)

        assert Path(file_path).exists()
        assert "idea-001" in str(file_path) or "idea-1" in str(file_path)

    def test_get_idea_files(self, service, tmp_path):
        """Test getting list of idea files."""
        ideas_dir = tmp_path / "test-project" / "ideas"
        (ideas_dir / "idea-001.md").write_text("Idea 1")
        (ideas_dir / "idea-002.md").write_text("Idea 2")
        (ideas_dir / "idea-003.md").write_text("Idea 3")

        files = service.get_idea_files("test-project")

        assert len(files) == 3
        assert any("idea-001" in f for f in files)

    def test_get_idea_files_empty(self, service):
        """Test getting idea files from empty directory."""
        files = service.get_idea_files("test-project")

        assert files == []


class TestResearchOperations:
    """Tests for research file operations."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create file service with temp directory."""
        with patch("api.services.file_operations.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            from api.services.file_operations import FileOperationsService

            service = FileOperationsService()
            # Create project with research directory
            project_dir = tmp_path / "test-project"
            (project_dir / "research").mkdir(parents=True)
            return service

    @pytest.mark.asyncio
    async def test_save_research_file(self, service, tmp_path):
        """Test saving a research file."""
        project_id = "test-project"
        content = "# Research Summary\n\nFindings here."

        await service.save_research_file(
            project_id,
            category="01-mercado",
            filename="market-analysis.md",
            content=content,
        )

        file_path = tmp_path / project_id / "research" / "01-mercado" / "market-analysis.md"
        assert file_path.exists()
        assert file_path.read_text() == content

    def test_get_research_files(self, service, tmp_path):
        """Test getting research files."""
        research_dir = tmp_path / "test-project" / "research"
        category_dir = research_dir / "01-mercado"
        category_dir.mkdir(parents=True)
        (category_dir / "file1.md").write_text("Research 1")
        (category_dir / "file2.md").write_text("Research 2")

        files = service.get_research_files("test-project")

        assert len(files) >= 2


class TestFileServiceSingleton:
    """Tests for singleton access."""

    def test_get_file_service_returns_same_instance(self, tmp_path):
        """Test singleton pattern."""
        with patch("api.services.file_operations.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            # Reset singleton
            import api.services.file_operations
            api.services.file_operations._file_service = None

            from api.services.file_operations import get_file_service

            service1 = get_file_service()
            service2 = get_file_service()

            assert service1 is service2


class TestFileServiceErrorHandling:
    """Tests for error handling."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create file service with temp directory."""
        with patch("api.services.file_operations.get_settings") as mock_settings:
            mock_settings.return_value.projects_dir = tmp_path

            from api.services.file_operations import FileOperationsService

            return FileOperationsService()

    @pytest.mark.asyncio
    async def test_read_file_invalid_project(self, service):
        """Test reading from non-existent project."""
        with pytest.raises(Exception):
            await service.read_file("nonexistent-project", "file.md")

    def test_get_metadata_invalid_json(self, service, tmp_path):
        """Test getting metadata with invalid JSON."""
        project_dir = tmp_path / "bad-metadata"
        project_dir.mkdir()
        (project_dir / "metadata.json").write_text("not valid json {{{")

        metadata = service.get_project_metadata("bad-metadata")

        # Should return empty dict on error
        assert metadata == {}
