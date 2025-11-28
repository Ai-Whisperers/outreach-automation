"""
Research management routes.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import APIKeyDep, FileServiceDep, ResearchServiceDep, SynthesisServiceDep
from ..exceptions import FileNotFoundError, ProjectNotFoundError, SourceFetchError
from ..logging_config import get_logger
from ..models import (
    ResearchAddRequest,
    ResearchAddResponse,
    ResearchSource,
    SynthesizeRequest,
    SynthesizeResponse,
)


class AutoResearchRequest(BaseModel):
    """Request for automatic research fetching."""
    num_queries: int = Field(default=10, ge=5, le=20)
    results_per_query: int = Field(default=3, ge=1, le=5)
    focus_areas: list[str] | None = None

router = APIRouter(prefix="/projects/{project_id}/research", tags=["research"])
logger = get_logger("routes.research")


@router.post("", response_model=ResearchAddResponse)
async def add_research(
    project_id: str,
    request: ResearchAddRequest,
    files: FileServiceDep,
    research: ResearchServiceDep
):
    """
    Add research sources to a project.

    Fetches content from URLs, summarizes with AI, and saves as markdown files.
    """
    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, FileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    # Add research
    result = await research.add_research(project_id, request.sources)

    logger.info(f"Added {result.added_count} sources to project: {project_id}")

    return result


@router.get("")
async def list_research(
    project_id: str,
    files: FileServiceDep,
    category: str = None
):
    """
    List research files in a project.

    Optionally filter by category.
    """
    try:
        research_files = files.get_research_files(project_id, category)
    except (ProjectNotFoundError, FileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied listing research for project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    return {
        "project_id": project_id,
        "category": category,
        "files": research_files,
        "count": len(research_files)
    }


@router.get("/sources")
async def get_sources(
    project_id: str,
    files: FileServiceDep
):
    """
    Get all tracked sources for a project.
    """
    try:
        sources = await files.load_sources(project_id)
    except (ProjectNotFoundError, FileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied loading sources for project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    return {
        "project_id": project_id,
        "sources": sources,
        "count": len(sources)
    }


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_research(
    project_id: str,
    files: FileServiceDep,
    synthesis: SynthesisServiceDep,
    api_key: APIKeyDep,
    request: SynthesizeRequest = None
):
    """
    Synthesize research into actionable insights.

    Generates:
    - Quick reference for brainstorming
    - Key insights (problem-reality-opportunity)
    - Do's and don'ts
    """
    if request is None:
        request = SynthesizeRequest()

    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, FileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    # Synthesize
    result = await synthesis.synthesize(
        project_id,
        include_quick_reference=request.include_quick_reference,
        include_insights=request.include_insights,
        include_dos_donts=request.include_dos_donts
    )

    logger.info(f"Synthesized research for project: {project_id}")

    return result


@router.get("/quick-reference")
async def get_quick_reference(project_id: str):
    """
    Get the quick reference for a project.
    """
    files = get_file_service()

    try:
        content = await files.read_file(project_id, "quick-reference.md")
    except (CustomFileNotFoundError, FileNotFoundError):
        raise HTTPException(
            status_code=404,
            detail="Quick reference not found. Run synthesis first."
        )
    except PermissionError as e:
        logger.error(f"Permission denied reading quick reference: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    return {
        "project_id": project_id,
        "content": content
    }


@router.post("/auto-fetch")
async def auto_fetch_research(project_id: str, request: AutoResearchRequest = None):
    """
    Automatically generate queries, search the web, and fetch research.

    This is a convenience endpoint that:
    1. Generates search queries based on the brief
    2. Performs web searches
    3. Fetches and summarizes content from results
    4. Saves everything as research files
    """
    if request is None:
        request = AutoResearchRequest()

    files = get_file_service()
    iteration = get_iteration_service()
    search = get_web_search_service()
    research = get_research_service()

    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, CustomFileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    # Step 1: Generate search queries
    logger.info(f"Generating {request.num_queries} search queries for project: {project_id}")
    queries_result = await iteration.generate_search_queries(
        project_id=project_id,
        focus_areas=request.focus_areas,
        num_queries=request.num_queries
    )

    queries = queries_result.get("queries", [])
    if not queries:
        return {
            "project_id": project_id,
            "status": "no_queries",
            "message": "Could not generate search queries"
        }

    # Step 2: Perform web searches
    logger.info(f"Searching for {len(queries)} queries...")
    search_results = await search.search_multiple(
        queries=queries,
        results_per_query=request.results_per_query
    )

    if not search_results:
        return {
            "project_id": project_id,
            "status": "no_results",
            "queries_generated": len(queries),
            "message": "Web search returned no results"
        }

    # Step 3: Convert search results to research sources
    sources = []
    seen_urls = set()

    for result in search_results:
        url = result.get("url", "")

        # Skip duplicates
        if url in seen_urls:
            continue
        seen_urls.add(url)

        sources.append(ResearchSource(
            url=url,
            title=result.get("title", "Untitled"),
            category=result.get("category", "01-mercado-general"),
            type="web"
        ))

    # Step 4: Fetch and process sources
    logger.info(f"Fetching {len(sources)} research sources...")

    try:
        result = await research.add_research(project_id, sources)
    except SourceFetchError as e:
        logger.error(f"Research fetching failed: {e}")
        return {
            "project_id": project_id,
            "status": "partial",
            "queries_generated": len(queries),
            "search_results": len(search_results),
            "error": str(e)
        }
    except OSError as e:
        logger.error(f"IO error during research fetching: {e}")
        return {
            "project_id": project_id,
            "status": "partial",
            "queries_generated": len(queries),
            "search_results": len(search_results),
            "error": f"IO error: {str(e)}"
        }

    return {
        "project_id": project_id,
        "status": "complete",
        "queries_generated": len(queries),
        "search_results": len(search_results),
        "sources_added": result.added_count,
        "files_created": result.files_created
    }


class AgentResearchRequest(BaseModel):
    """Request for agent-based research."""
    topic: str
    subtopics: list[str]


@router.post("/agent")
async def run_research_agent(project_id: str, request: AgentResearchRequest):
    """
    Run the LangGraph Research Agent.
    
    This agent dynamically plans and executes research:
    1. Generates queries based on topic
    2. Executes searches
    3. Analyzes results
    4. Decides if more info is needed
    5. Loops until satisfied
    """
    # Import here to avoid circular dependencies if any
    import sys
    from pathlib import Path
    # Ensure we can import the agent
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from api.agents.research_agent import create_research_graph

    agent = create_research_graph()

    initial_state = {
        "project_id": project_id,
        "topic": request.topic,
        "subtopics": request.subtopics,
        "messages": [],
        "findings": [],
        "pending_queries": [],
        "iterations": 0,
        "is_complete": False
    }

    logger.info(f"Starting Research Agent for project {project_id} on topic: {request.topic}")

    final_state = await agent.ainvoke(initial_state)

    # Save findings to a file
    files = get_file_service()
    content = f"# Agent Research: {request.topic}\n\n"
    content += f"**Subtopics:** {', '.join(request.subtopics)}\n\n"
    content += "## Findings\n\n"
    content += "\n\n".join(final_state["findings"])

    filename = f"research/agent-{request.topic.lower().replace(' ', '-')}.md"
    await files.write_file(project_id, filename, content)

    return {
        "project_id": project_id,
        "status": "complete",
        "iterations": final_state["iterations"],
        "findings_count": len(final_state["findings"]),
        "output_file": filename
    }
