"""
Celery tasks for idea generation.
"""

import asyncio

from celery import Task

from ..services.ideas_service import get_ideas_service
from .celery_app import celery_app


class AsyncTask(Task):
    """Base task that supports async functions."""

    def __call__(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.run(*args, **kwargs))


@celery_app.task(base=AsyncTask, bind=True, name="tasks.generate_ideas")
async def generate_ideas_task(self, project_id: str, num_ideas: int = 25):
    """
    Generate ideas for a project (async task).
    
    Args:
        project_id: Project ID
        num_ideas: Number of ideas to generate
    
    Returns:
        dict with generation results
    """
    self.update_state(state="PROGRESS", meta={"status": "Starting idea generation"})

    ideas_service = get_ideas_service()

    try:
        result = await ideas_service.generate_ideas(
            project_id=project_id,
            num_ideas=num_ideas
        )

        return {
            "status": "completed",
            "project_id": project_id,
            "ideas_generated": result.ideas_generated,
            "files_created": result.files_created
        }

    except Exception as e:
        self.update_state(state="FAILURE", meta={"error": str(e)})
        raise


@celery_app.task(base=AsyncTask, name="tasks.score_ideas")
async def score_ideas_task(project_id: str):
    """
    Score all ideas for a project (async task).
    
    Args:
        project_id: Project ID
    
    Returns:
        dict with scoring results
    """
    ideas_service = get_ideas_service()

    try:
        result = await ideas_service.score_all_ideas(project_id=project_id)

        return {
            "status": "completed",
            "project_id": project_id,
            "total_ideas": result.total_ideas,
            "tier_distribution": result.tier_distribution
        }

    except Exception:
        raise


@celery_app.task(base=AsyncTask, name="tasks.generate_and_score")
async def generate_and_score_task(project_id: str, num_ideas: int = 25):
    """
    Generate and score ideas in one task.
    
    Args:
        project_id: Project ID
        num_ideas: Number of ideas to generate
    
    Returns:
        dict with combined results
    """
    # Generate ideas
    gen_result = await generate_ideas_task.run(project_id, num_ideas)

    # Score ideas
    score_result = await score_ideas_task.run(project_id)

    return {
        "status": "completed",
        "generation": gen_result,
        "scoring": score_result
    }
