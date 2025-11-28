"""
Repository pattern for database access.
"""


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Idea, Project, ResearchItem


class ProjectRepository:
    """Repository for Project operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, project: Project) -> Project:
        """Create a new project."""
        self.session.add(project)
        await self.session.flush()
        return project

    async def get(self, project_id: str) -> Project | None:
        """Get project by ID."""
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def list(self, limit: int = 100, offset: int = 0) -> list[Project]:
        """List all projects."""
        result = await self.session.execute(
            select(Project)
            .order_by(Project.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update(self, project: Project) -> Project:
        """Update project."""
        await self.session.flush()
        return project

    async def delete(self, project_id: str) -> bool:
        """Delete project."""
        project = await self.get(project_id)
        if project:
            await self.session.delete(project)
            await self.session.flush()
            return True
        return False


class IdeaRepository:
    """Repository for Idea operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, idea: Idea) -> Idea:
        """Create a new idea."""
        self.session.add(idea)
        await self.session.flush()
        return idea

    async def get(self, idea_id: int) -> Idea | None:
        """Get idea by ID."""
        result = await self.session.execute(
            select(Idea).where(Idea.id == idea_id)
        )
        return result.scalar_one_or_none()

    async def list_by_project(
        self,
        project_id: str,
        limit: int = 100
    ) -> list[Idea]:
        """List ideas for a project."""
        result = await self.session.execute(
            select(Idea)
            .where(Idea.project_id == project_id)
            .order_by(Idea.number)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_next_number(self, project_id: str) -> int:
        """Get next idea number for project."""
        result = await self.session.execute(
            select(func.max(Idea.number))
            .where(Idea.project_id == project_id)
        )
        max_number = result.scalar()
        return (max_number or 0) + 1

    async def get_top_ideas(
        self,
        project_id: str,
        limit: int = 10
    ) -> list[Idea]:
        """Get top-scored ideas."""
        result = await self.session.execute(
            select(Idea)
            .where(Idea.project_id == project_id)
            .order_by(Idea.overall_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class ResearchRepository:
    """Repository for ResearchItem operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, item: ResearchItem) -> ResearchItem:
        """Create a new research item."""
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_by_project(
        self,
        project_id: str,
        category: str | None = None
    ) -> list[ResearchItem]:
        """List research items for a project."""
        query = select(ResearchItem).where(
            ResearchItem.project_id == project_id
        )

        if category:
            query = query.where(ResearchItem.category == category)

        query = query.order_by(ResearchItem.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_by_category(
        self,
        project_id: str
    ) -> dict[str, int]:
        """Count research items by category."""
        result = await self.session.execute(
            select(
                ResearchItem.category,
                func.count(ResearchItem.id)
            )
            .where(ResearchItem.project_id == project_id)
            .group_by(ResearchItem.category)
        )
        return {category: count for category, count in result.all()}
