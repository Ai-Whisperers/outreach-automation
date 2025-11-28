"""
Research Service

Processes and summarizes research content for campaigns.
"""

from datetime import datetime
from typing import Any

from ..logging_config import get_logger
from ..models import ResearchAddResponse, ResearchSource, ResearchSummary
from .ai_client import get_ai_manager, get_prompt_loader
from .file_operations import get_file_service
from .template_renderer import get_template_renderer
from .web_fetcher import get_web_fetcher

logger = get_logger("research_service")


# =============================================================================
# Research Service
# =============================================================================

class ResearchService:
    """
    Service for processing and summarizing research content.
    """

    def __init__(self, research_repository: Any | None = None):
        self.ai = get_ai_manager()
        self.prompts = get_prompt_loader()
        self.files = get_file_service()
        self.renderer = get_template_renderer()
        self.fetcher = get_web_fetcher()
        self.research_repository = research_repository

    async def add_research(
        self,
        project_id: str,
        sources: list[ResearchSource]
    ) -> ResearchAddResponse:
        """
        Add research sources to a project.

        Args:
            project_id: Project identifier
            sources: List of research sources

        Returns:
            Response with added files info
        """
        logger.info(f"Adding {len(sources)} sources to project: {project_id}")

        files_created = []
        sources_tracked = []

        for source in sources:
            # Fetch content if URL provided
            content = source.content
            title = source.title

            if source.url and not content:
                try:
                    fetched = await self.fetcher.fetch_url(str(source.url))
                    content = fetched.get("content", "")
                    title = fetched.get("title", title)
                except Exception as e:
                    logger.warning(f"Failed to fetch {source.url}: {e}")
                    content = f"[Failed to fetch: {e}]"

            # Summarize content
            summary = await self._summarize_content(content, source.category)

            # Extract statistics
            statistics = await self._extract_statistics(content)

            # Classify source type
            source_type = source.type
            if source.url:
                source_type = self.fetcher.classify_source_type(
                    str(source.url),
                    content
                )

            # Generate filename
            filename = self._generate_filename(title)

            # Render research file
            rendered = self.renderer.render_research_file(
                title=title,
                category=source.category,
                content=summary.summary,
                sources=[{
                    "url": str(source.url) if source.url else "",
                    "title": title,
                    "type": source_type,
                    "accessed": datetime.utcnow().strftime("%Y-%m-%d")
                }],
                key_statistics=[s.get("text", "") for s in statistics[:5]]
            )

            # Save file
            file_path = await self.files.save_research_file(
                project_id,
                source.category,
                filename,
                rendered
            )
            files_created.append(str(file_path))

            # Save to database if repository available
            if self.research_repository:
                try:
                    from ..database.models import ResearchItem

                    db_research = ResearchItem(
                        project_id=project_id,
                        category=source.category,
                        title=title,
                        source_url=str(source.url) if source.url else None,
                        source_type=source_type,
                        file_path=str(file_path),
                        relevance_score=summary.relevance_score,
                        created_at=datetime.utcnow()
                    )
                    await self.research_repository.create(db_research)
                    logger.debug(f"Saved research item to database: {title}")
                except Exception as e:
                    logger.warning(f"Failed to save research to database: {e}")

            # Track source
            source_record = {
                "title": title,
                "url": str(source.url) if source.url else None,
                "type": source_type,
                "category": source.category,
                "date_accessed": datetime.utcnow().strftime("%Y-%m-%d"),
                "reliability": self._assess_reliability(source_type),
                "key_data": [s.get("text", "") for s in statistics[:3]]
            }
            await self.files.add_source(project_id, source_record)
            sources_tracked.append(source_record)

        # Update project status
        self.files.update_project_metadata(project_id, {
            "status": "researching",
            "research_count": len(files_created)
        })

        logger.info(f"Added {len(files_created)} research files to project: {project_id}")

        return ResearchAddResponse(
            project_id=project_id,
            added_count=len(sources),
            files_created=[f.split("/")[-1] for f in files_created],
            sources_tracked=len(sources_tracked)
        )

    async def _summarize_content(self, content: str, category: str) -> ResearchSummary:
        """
        Summarize research content using AI.

        Args:
            content: Raw content to summarize
            category: Research category

        Returns:
            Summarized content
        """
        logger.debug(f"Summarizing content for category: {category}")

        system, user = self.prompts.format(
            "research", "summary",
            content=content,
            research_category=category
        )

        response = await self.ai.generate_json(
            prompt=user,
            system=system,
            temperature=0.3
        )

        return ResearchSummary(
            title=response.get("title", "Research Summary"),
            summary=response.get("summary", ""),
            key_points=response.get("key_points", []),
            statistics=response.get("statistics", []),
            relevance_score=response.get("relevance_score", 5.0),
            source_type=response.get("source_type", "web")
        )

    async def _extract_statistics(self, content: str) -> list[dict[str, Any]]:
        """
        Extract key statistics from content.

        Args:
            content: Content to analyze

        Returns:
            List of statistic dicts
        """
        logger.debug("Extracting statistics from content")

        system, user = self.prompts.format(
            "research", "statistics",
            content=content
        )

        response = await self.ai.generate_json(
            prompt=user,
            system=system,
            temperature=0.2
        )

        return response.get("statistics", [])

    def _generate_filename(self, title: str) -> str:
        """
        Generate a safe filename from title.

        Args:
            title: Source title

        Returns:
            Safe filename without extension
        """
        # Remove special characters
        safe = "".join(c if c.isalnum() or c in " -_" else "" for c in title)

        # Convert to lowercase and replace spaces
        safe = safe.lower().strip().replace(" ", "-")

        # Remove multiple dashes
        while "--" in safe:
            safe = safe.replace("--", "-")

        # Limit length
        if len(safe) > 50:
            safe = safe[:50].rsplit("-", 1)[0]

        return safe or "research"

    def _assess_reliability(self, source_type: str) -> str:
        """
        Assess reliability of source based on type.

        Args:
            source_type: Type of source

        Returns:
            Reliability level (high, medium, low)
        """
        high_reliability = ["industry_report", "academic", "government"]
        medium_reliability = ["market_data", "news_article"]

        if source_type in high_reliability:
            return "high"
        elif source_type in medium_reliability:
            return "medium"
        else:
            return "low"

    async def get_all_research(self, project_id: str) -> str:
        """
        Get all research content combined.

        Args:
            project_id: Project identifier

        Returns:
            Combined research content
        """
        research_files = self.files.get_research_files(project_id)
        combined = []

        for file_path in research_files:
            content = await self.files.read_file(project_id, file_path)
            combined.append(f"## {file_path}\n\n{content}")

        return "\n\n---\n\n".join(combined)


# =============================================================================
# Singleton Access
# =============================================================================

_research_service: ResearchService | None = None


def get_research_service() -> ResearchService:
    """Get singleton research service."""
    global _research_service
    if _research_service is None:
        _research_service = ResearchService()
    return _research_service
