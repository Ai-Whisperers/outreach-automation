"""
Celery tasks for research automation.
"""

import asyncio

from celery import Task

from ..services.research_automation import get_research_automation_service
from .celery_app import celery_app


class AsyncTask(Task):
    """Base task that supports async functions."""

    def __call__(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.run(*args, **kwargs))


@celery_app.task(base=AsyncTask, bind=True, name="tasks.auto_research")
async def auto_research_task(self, project_id: str, categories: list[str] = None):
    """
    Run automated research for a project (async task).

    Args:
        project_id: Project ID
        categories: Optional list of categories to research

    Returns:
        dict with research results
    """
    self.update_state(state="PROGRESS", meta={"status": "Starting research automation"})

    automation = get_research_automation_service()

    try:
        result = await automation.run_full_research(project_id=project_id, categories=categories)

        return {
            "status": "completed",
            "project_id": project_id,
            "files_created": result.files_created,
            "total_sources": result.total_sources,
        }

    except Exception as e:
        self.update_state(state="FAILURE", meta={"error": str(e)})
        raise
