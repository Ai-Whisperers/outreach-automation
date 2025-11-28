"""
Ideas generation and management routes.
"""

from fastapi import APIRouter, HTTPException

from ..agents.ideation_agent import create_ideation_graph
from ..dependencies import APIKeyDep, FileServiceDep, IdeasServiceDep
from ..exceptions import FileNotFoundError as CustomFileNotFoundError
from ..exceptions import ProjectNotFoundError
from ..logging_config import get_logger
from ..models import (
    IdeaExpandRequest,
    IdeaExpandResponse,
    IdeaGenerateRequest,
    IdeaGenerateResponse,
    IdeaScoreRequest,
    IdeaScoreResponse,
)

router = APIRouter(prefix="/projects/{project_id}/ideas", tags=["ideas"])
logger = get_logger("routes.ideas")


@router.post("/generate", response_model=IdeaGenerateResponse)
async def generate_ideas(
    project_id: str,
    files: FileServiceDep,
    ideas: IdeasServiceDep,
    api_key: APIKeyDep,
    request: IdeaGenerateRequest = None,
):
    """
    Generate campaign idea concepts.

    Creates multiple idea concepts based on research and brief.
    Ideas are generated in batches for better quality.
    """
    if request is None:
        request = IdeaGenerateRequest()

    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, CustomFileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    # Generate ideas
    result = await ideas.generate_ideas(
        project_id=project_id,
        num_ideas=request.num_ideas,
        batch_size=request.batch_size,
        creative_directions=request.creative_directions,
    )

    logger.info(f"Generated {result.ideas_generated} ideas for project: {project_id}")

    return result


@router.post("/agent", response_model=IdeaGenerateResponse)
async def generate_ideas_agent(
    project_id: str, files: FileServiceDep, api_key: APIKeyDep, request: IdeaGenerateRequest = None
):
    """
    Generate campaign ideas using the Ideation Agent (LangGraph).

    Uses a Brainstorm-Critique-Refine loop to produce higher quality ideas.
    """
    if request is None:
        request = IdeaGenerateRequest()

    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, CustomFileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    # Load brief
    try:
        brief_text = await files.read_file(project_id, "brief-expanded.md")
    except (CustomFileNotFoundError, FileNotFoundError):
        try:
            brief_text = await files.read_file(project_id, "brief-original.md")
        except (CustomFileNotFoundError, FileNotFoundError):
            raise HTTPException(
                status_code=400, detail="Brief not found. Please parse brief first."
            )

    # Load research summary (optional)
    try:
        research_summary = await files.read_file(project_id, "research/summary.md")
    except (CustomFileNotFoundError, FileNotFoundError):
        research_summary = ""

    # Initialize Agent
    graph = create_ideation_graph()

    initial_state = {
        "project_id": project_id,
        "brief_text": brief_text,
        "research_summary": research_summary,
        "ideas": [],
        "critique": "",
        "iteration_count": 0,
        "max_iterations": 1,  # Default to 1 iteration for now
    }

    # Run Agent
    logger.info(f"Starting Ideation Agent for project: {project_id}")
    final_state = await graph.ainvoke(initial_state)

    # Save ideas using existing service logic (to handle numbering and file saving)
    # We need to convert Idea objects to the format expected by save_idea or just save manually
    # The IdeasService.generate_ideas does generation + saving.
    # Here we have the ideas, we just need to save them.

    saved_ideas = []
    for idea in final_state["ideas"]:
        # Format as markdown
        content = f"# {idea.title}\n\n{idea.description}\n\n## Rationale\n{idea.rationale}"

        # Get next number
        next_num = files.get_next_idea_number(project_id)

        # Save file
        path = await files.save_idea(project_id, next_num, content)
        saved_ideas.append(str(path))

    return IdeaGenerateResponse(
        project_id=project_id, ideas_generated=len(saved_ideas), ideas=saved_ideas
    )


@router.post("/expand", response_model=IdeaExpandResponse)
async def expand_idea(
    project_id: str, request: IdeaExpandRequest, files: FileServiceDep, api_key: APIKeyDep
):
    """
    Expand an idea with full details and scoring.

    Takes a concept and develops it into a complete idea with:
    - Detailed execution per format
    - Full scoring across 10 criteria
    - Strengths and weaknesses analysis
    - Recommendations
    """
    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, CustomFileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    # For now, we need the concept to be passed
    # In a full implementation, we'd load from generated concepts
    raise HTTPException(
        status_code=400, detail="Please use /expand-all to expand all generated ideas"
    )


@router.post("/expand-all")
async def expand_all_ideas(project_id: str, files: FileServiceDep, api_key: APIKeyDep):
    """
    Expand all generated ideas with full details.

    This is typically called after generate_ideas to develop
    all concepts into complete ideas with scoring.
    """
    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, CustomFileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    # First generate ideas if not already done
    # Then expand each one
    # First generate ideas if not already done
    # Then expand each one

    # TODO: Implement internal orchestration for expanding all ideas
    return {"status": "pending", "message": "Batch expansion not yet implemented internally."}


@router.post("/score", response_model=IdeaScoreResponse)
async def score_ideas(
    project_id: str,
    files: FileServiceDep,
    ideas: IdeasServiceDep,
    api_key: APIKeyDep,
    request: IdeaScoreRequest = None,
):
    """
    Score and rank all ideas in a project.

    Analyzes all expanded ideas and:
    - Calculates weighted scores
    - Assigns tier classifications
    - Generates rankings
    - Creates summary document
    """
    if request is None:
        request = IdeaScoreRequest()

    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, CustomFileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    # Score all ideas
    result = await ideas.score_all_ideas(project_id=project_id, recalculate=request.recalculate)

    logger.info(f"Scored {result.total_ideas} ideas for project: {project_id}")

    return result


@router.get("")
async def list_ideas(project_id: str, files: FileServiceDep):
    """
    List all ideas in a project.
    """
    try:
        idea_files = files.get_idea_files(project_id)
    except (ProjectNotFoundError, CustomFileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    return {"project_id": project_id, "ideas": idea_files, "count": len(idea_files)}


@router.get("/{idea_number}")
async def get_idea(project_id: str, idea_number: int, files: FileServiceDep):
    """
    Get a specific idea by number.
    """
    try:
        filename = f"ideas/idea-{idea_number:03d}.md"
        content = await files.read_file(project_id, filename)
    except (CustomFileNotFoundError, FileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Idea {idea_number} not found in project")
    except PermissionError as e:
        logger.error(f"Permission denied reading idea {idea_number}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    return {"project_id": project_id, "idea_number": idea_number, "content": content}


@router.get("/summary")
async def get_ideas_summary(project_id: str, files: FileServiceDep):
    """
    Get the ideas summary and rankings.
    """
    try:
        content = await files.read_file(project_id, "ideas-summary.md")
    except (CustomFileNotFoundError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Ideas summary not found. Run scoring first.")
    except PermissionError as e:
        logger.error(f"Permission denied reading ideas summary: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    return {"project_id": project_id, "content": content}
