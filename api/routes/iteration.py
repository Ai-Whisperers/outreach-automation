"""
Iteration Routes

API endpoints for iterative research and idea improvement loops.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..logging_config import get_logger
from ..services.iteration_service import IterationError, get_iteration_service

logger = get_logger("routes.iteration")
router = APIRouter(prefix="/projects/{project_id}", tags=["iteration"])


# =============================================================================
# Request/Response Models
# =============================================================================

class GenerateQueriesRequest(BaseModel):
    """Request to generate search queries."""
    focus_areas: list[str] | None = Field(
        default=None,
        description="Specific categories to focus on"
    )
    num_queries: int = Field(
        default=10,
        ge=5,
        le=30,
        description="Number of queries to generate"
    )


class TargetedIdeaRequest(BaseModel):
    """Request to generate targeted ideas."""
    focus: str = Field(
        ...,
        description="What to focus on (e.g., 'viral_potential', 'PR_hooks', 'memorability')"
    )
    avoid_similar_to: list[int] | None = Field(
        default=None,
        description="Idea numbers to avoid duplicating"
    )
    num_ideas: int = Field(
        default=10,
        ge=3,
        le=25,
        description="Number of ideas to generate"
    )


class CombineIdeasRequest(BaseModel):
    """Request to combine ideas."""
    idea_numbers: list[int] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="Idea numbers to combine"
    )
    direction: str | None = Field(
        default=None,
        description="Optional guidance for the combination"
    )


# =============================================================================
# Research Iteration Endpoints
# =============================================================================

@router.post("/research/analyze-gaps")
async def analyze_research_gaps(project_id: str):
    """
    Analyze research coverage and identify gaps.

    Returns coverage score, missing areas, and suggested queries
    to fill the gaps.
    """
    try:
        service = get_iteration_service()
        result = await service.analyze_research_gaps(project_id)

        return {
            "project_id": project_id,
            **result
        }

    except IterationError as e:
        logger.error(f"Research gap analysis failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in research gap analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.post("/research/generate-queries")
async def generate_search_queries(
    project_id: str,
    request: GenerateQueriesRequest = None
):
    """
    Generate search queries based on brief and research gaps.

    AI generates targeted search queries in Spanish and English
    to find relevant research sources.
    """
    try:
        service = get_iteration_service()

        if request is None:
            request = GenerateQueriesRequest()

        result = await service.generate_search_queries(
            project_id=project_id,
            focus_areas=request.focus_areas,
            num_queries=request.num_queries
        )

        return {
            "project_id": project_id,
            **result
        }

    except IterationError as e:
        logger.error(f"Query generation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in query generation: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


# =============================================================================
# Idea Iteration Endpoints
# =============================================================================

@router.post("/ideas/analyze-gaps")
async def analyze_idea_gaps(project_id: str):
    """
    Analyze idea quality and identify improvement opportunities.

    Returns quality distribution, weak dimensions, coverage gaps,
    and recommendations for generating additional ideas.
    """
    try:
        service = get_iteration_service()
        result = await service.analyze_idea_gaps(project_id)

        return {
            "project_id": project_id,
            **result
        }

    except IterationError as e:
        logger.error(f"Idea gap analysis failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in idea gap analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.post("/ideas/generate-targeted")
async def generate_targeted_ideas(
    project_id: str,
    request: TargetedIdeaRequest
):
    """
    Generate ideas focused on specific dimensions or gaps.

    Use this after analyze-gaps to generate ideas that specifically
    address weak scoring dimensions or missing creative directions.
    """
    try:
        service = get_iteration_service()
        result = await service.generate_targeted_ideas(
            project_id=project_id,
            focus=request.focus,
            avoid_similar_to=request.avoid_similar_to,
            num_ideas=request.num_ideas
        )

        return {
            "project_id": project_id,
            **result
        }

    except IterationError as e:
        logger.error(f"Targeted idea generation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in targeted generation: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


@router.post("/ideas/combine")
async def combine_ideas(
    project_id: str,
    request: CombineIdeasRequest
):
    """
    Combine multiple ideas into a stronger unified concept.

    AI takes the best elements from each idea and creates
    a new, stronger concept that resolves contradictions
    and maximizes impact.
    """
    try:
        service = get_iteration_service()
        result = await service.combine_ideas(
            project_id=project_id,
            idea_numbers=request.idea_numbers,
            direction=request.direction
        )

        return {
            "project_id": project_id,
            **result
        }

    except IterationError as e:
        logger.error(f"Idea combination failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in idea combination: {e}")
        raise HTTPException(status_code=500, detail=f"Combination failed: {e}")
