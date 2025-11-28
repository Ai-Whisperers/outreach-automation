"""
File Operations Service

Handles all file system operations for projects, research, and ideas.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import yaml

from ..config import get_project_config, get_settings
from ..exceptions import FileNotFoundError, FileWriteError, ProjectNotFoundError
from ..logging_config import get_logger

logger = get_logger("file_operations")


# =============================================================================
# File Operations Service
# =============================================================================

class FileOperationsService:
    """
    Service for managing project files and directories.
    
    Uses hybrid storage: database for metadata, files for content.
    """

    def __init__(
        self,
        projects_dir: Path | None = None,
        project_repository: Any | None = None
    ):
        """
        Initialize file operations service.

        Args:
            projects_dir: Base directory for projects
            project_repository: Optional repository for database operations
        """
        if projects_dir is None:
            settings = get_settings()
            projects_dir = settings.projects_dir

        self.projects_dir = projects_dir
        self.config = get_project_config()
        self.project_repository = project_repository

        # Ensure projects directory exists
        self.projects_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"File operations service initialized: {projects_dir}")

    # =========================================================================
    # Project Operations
    # =========================================================================

    async def create_project_structure(
        self,
        project_id: str,
        project_name: str,
        client: str = "",
        country: str | None = None,
        language: str | None = None,
        campaign_type: str = "social"
    ) -> dict[str, Any]:
        """
        Create directory structure for a new project.
        
        Saves metadata to database (if available) and creates file structure.

        Args:
            project_id: Unique project identifier
            project_name: Human-readable project name
            client: Client name
            country: Country code
            language: Language code
            campaign_type: Type of campaign

        Returns:
            Project metadata dictionary
        """
        project_dir = self.projects_dir / project_id

        if project_dir.exists():
            logger.warning(f"Project directory already exists: {project_id}")
        else:
            project_dir.mkdir(parents=True)

        # Create research category directories
        for category in self.config.research.categories:
            (project_dir / category.id).mkdir(exist_ok=True)

        # Create ideas directory
        (project_dir / "ideas").mkdir(exist_ok=True)

        # Create exports directory
        (project_dir / "exports").mkdir(exist_ok=True)

        # Create project metadata
        now = datetime.utcnow()
        metadata = {
            "id": project_id,
            "name": project_name,
            "client": client,
            "country": country or getattr(self.config, "default_country", "Paraguay"),
            "language": language or getattr(self.config, "default_language", "es"),
            "campaign_type": campaign_type,
            "status": "created",
            "created_at": now.isoformat() + "Z",
            "brief_parsed": False,
            "brief_file_path": None
        }

        # Save to database if repository available
        if self.project_repository:
            try:
                from ..database.models import Project
                db_project = Project(
                    id=project_id,
                    name=project_name,
                    client=client,
                    country=metadata["country"],
                    language=metadata["language"],
                    campaign_type=campaign_type,
                    status="created",
                    created_at=now,
                    brief_parsed=False
                )
                await self.project_repository.create(db_project)
                logger.info(f"Saved project to database: {project_id}")
            except Exception as e:
                logger.warning(f"Failed to save project to database: {e}")
                # Continue with file-only mode

        # Save metadata file (backward compatibility)
        metadata_path = project_dir / "project.yaml"
        with open(metadata_path, "w", encoding="utf-8") as f:
            yaml.dump(metadata, f, allow_unicode=True, default_flow_style=False)

        logger.info(f"Created project structure: {project_id}")
        return metadata

    def get_project_path(self, project_id: str) -> Path:
        """
        Get path to project directory.

        Args:
            project_id: Project identifier

        Returns:
            Path to project directory

        Raises:
            ProjectNotFoundError: If project doesn't exist
        """
        project_dir = self.projects_dir / project_id

        if not project_dir.exists():
            raise ProjectNotFoundError(project_id)

        return project_dir

    def list_projects(self) -> list[dict[str, Any]]:
        """
        List all projects with basic metadata.

        Returns:
            List of project metadata dicts
        """
        projects = []

        for item in self.projects_dir.iterdir():
            if item.is_dir():
                metadata_path = item / "project.yaml"
                if metadata_path.exists():
                    with open(metadata_path, encoding="utf-8") as f:
                        metadata = yaml.safe_load(f)
                        projects.append(metadata)

        # Sort by creation date (newest first)
        projects.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return projects

    def get_project_metadata(self, project_id: str) -> dict[str, Any]:
        """
        Get project metadata.

        Args:
            project_id: Project identifier

        Returns:
            Project metadata dict
        """
        project_dir = self.get_project_path(project_id)
        metadata_path = project_dir / "project.yaml"

        with open(metadata_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def update_project_metadata(self, project_id: str, updates: dict[str, Any]):
        """
        Update project metadata.

        Args:
            project_id: Project identifier
            updates: Dict of fields to update
        """
        project_dir = self.get_project_path(project_id)
        metadata_path = project_dir / "project.yaml"

        # Load existing metadata
        with open(metadata_path, encoding="utf-8") as f:
            metadata = yaml.safe_load(f)

        # Update fields
        metadata.update(updates)
        metadata["updated_at"] = datetime.utcnow().isoformat() + "Z"

        # Save
        with open(metadata_path, "w", encoding="utf-8") as f:
            yaml.dump(metadata, f, allow_unicode=True, default_flow_style=False)

        logger.debug(f"Updated metadata for project: {project_id}")

    def delete_project(self, project_id: str):
        """
        Delete a project and all its files.

        Args:
            project_id: Project identifier
        """
        project_dir = self.get_project_path(project_id)
        shutil.rmtree(project_dir)
        logger.info(f"Deleted project: {project_id}")

    # =========================================================================
    # File Operations
    # =========================================================================

    async def write_file(
        self,
        project_id: str,
        relative_path: str,
        content: str
    ) -> Path:
        """
        Write content to a file in project.

        Args:
            project_id: Project identifier
            relative_path: Path relative to project dir
            content: File content

        Returns:
            Absolute path to written file
        """
        project_dir = self.get_project_path(project_id)
        file_path = project_dir / relative_path

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)

            logger.debug(f"Wrote file: {relative_path}")
            return file_path

        except Exception as e:
            logger.error(f"Failed to write file {relative_path}: {e}")
            raise FileWriteError(str(file_path), str(e))

    async def read_file(self, project_id: str, relative_path: str) -> str:
        """
        Read content from a file in project.

        Args:
            project_id: Project identifier
            relative_path: Path relative to project dir

        Returns:
            File content
        """
        project_dir = self.get_project_path(project_id)
        file_path = project_dir / relative_path

        if not file_path.exists():
            raise FileNotFoundError(str(file_path))

        async with aiofiles.open(file_path, encoding="utf-8") as f:
            return await f.read()

    def list_files(
        self,
        project_id: str,
        directory: str = "",
        pattern: str = "*"
    ) -> list[str]:
        """
        List files in a project directory.

        Args:
            project_id: Project identifier
            directory: Subdirectory (empty for root)
            pattern: Glob pattern

        Returns:
            List of relative file paths
        """
        project_dir = self.get_project_path(project_id)
        search_dir = project_dir / directory if directory else project_dir
        logger.info(f"Searching for files in: {search_dir} with pattern: {pattern}")
        logger.info(f"Directory exists: {search_dir.exists()}")
        if search_dir.exists():
            logger.info(f"Directory contents: {[str(p.name) for p in search_dir.iterdir()]}")

        import fnmatch

        files = []
        if search_dir.exists():
            for file_path in search_dir.iterdir():
                is_match = fnmatch.fnmatch(file_path.name, pattern)
                logger.info(f"Checking {file_path.name}: match={is_match}")
                if file_path.is_file() and is_match:
                    relative = file_path.relative_to(project_dir)
                    files.append(str(relative))

        logger.info(f"Found {len(files)} files: {files}")
        return sorted(files)

    # =========================================================================
    # Research Operations
    # =========================================================================

    async def save_research_file(
        self,
        project_id: str,
        category: str,
        filename: str,
        content: str
    ) -> Path:
        """
        Save a research file.

        Args:
            project_id: Project identifier
            category: Research category (e.g., "01-mercado-general")
            filename: File name (without extension)
            content: Markdown content

        Returns:
            Path to saved file
        """
        relative_path = f"{category}/{filename}.md"
        return await self.write_file(project_id, relative_path, content)

    def get_research_files(self, project_id: str, category: str | None = None) -> list[str]:
        """
        Get list of research files.

        Args:
            project_id: Project identifier
            category: Optional category filter

        Returns:
            List of research file paths
        """
        if category:
            return self.list_files(project_id, category, "*.md")
        else:
            files = []
            for cat in self.config.research.categories:
                files.extend(self.list_files(project_id, cat.id, "*.md"))
            return files

    # =========================================================================
    # Ideas Operations
    # =========================================================================

    async def save_idea(
        self,
        project_id: str,
        idea_number: int,
        content: str
    ) -> Path:
        """
        Save an idea file.

        Args:
            project_id: Project identifier
            idea_number: Sequential idea number
            content: Markdown content

        Returns:
            Path to saved file
        """
        filename = f"idea-{idea_number:03d}.md"
        return await self.write_file(project_id, f"ideas/{filename}", content)

    def get_idea_files(self, project_id: str) -> list[str]:
        """
        Get list of idea files.

        Args:
            project_id: Project identifier

        Returns:
            List of idea file paths
        """
        return self.list_files(project_id, "ideas", "idea-*.md")

    def get_next_idea_number(self, project_id: str) -> int:
        """
        Get next available idea number.

        Args:
            project_id: Project identifier

        Returns:
            Next idea number
        """
        ideas = self.get_idea_files(project_id)

        if not ideas:
            return 1

        # Extract numbers from filenames
        numbers = []
        for idea_path in ideas:
            filename = Path(idea_path).stem  # "idea-001"
            try:
                num = int(filename.split("-")[1])
                numbers.append(num)
            except (IndexError, ValueError):
                continue

        return max(numbers) + 1 if numbers else 1

    # =========================================================================
    # Sources Operations
    # =========================================================================

    async def save_sources(self, project_id: str, sources: list[dict[str, Any]]):
        """
        Save sources tracking file.

        Args:
            project_id: Project identifier
            sources: List of source dicts
        """
        sources_data = {
            "project": project_id,
            "generated": datetime.utcnow().isoformat() + "Z",
            "total_sources": len(sources),
            "sources": sources
        }

        content = json.dumps(sources_data, indent=2, ensure_ascii=False)
        await self.write_file(project_id, "sources.json", content)

    async def load_sources(self, project_id: str) -> list[dict[str, Any]]:
        """
        Load sources from tracking file.

        Args:
            project_id: Project identifier

        Returns:
            List of source dicts
        """
        try:
            content = await self.read_file(project_id, "sources.json")
            data = json.loads(content)
            return data.get("sources", [])
        except FileNotFoundError:
            return []

    async def add_source(self, project_id: str, source: dict[str, Any]):
        """
        Add a source to tracking file.

        Args:
            project_id: Project identifier
            source: Source dict to add
        """
        sources = await self.load_sources(project_id)

        # Auto-assign ID
        max_id = max((s.get("id", 0) for s in sources), default=0)
        source["id"] = max_id + 1

        sources.append(source)
        await self.save_sources(project_id, sources)


# =============================================================================
# Singleton Access
# =============================================================================

_file_service: FileOperationsService | None = None


def get_file_service() -> FileOperationsService:
    """Get singleton file operations service."""
    global _file_service
    if _file_service is None:
        _file_service = FileOperationsService()
    return _file_service
