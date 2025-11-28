"""
Brief parsing routes.
"""

from fastapi import APIRouter, HTTPException

from ..dependencies import APIKeyDep, BriefParserDep, FileServiceDep
from ..exceptions import FileNotFoundError, ProjectNotFoundError
from ..logging_config import get_logger
from ..models import BriefParseResponse, BriefUpload

router = APIRouter(prefix="/projects/{project_id}/brief", tags=["brief"])
logger = get_logger("routes.brief")


@router.post("/parse", response_model=BriefParseResponse)
async def parse_brief(
    project_id: str,
    files: FileServiceDep,
    parser: BriefParserDep,
    api_key: APIKeyDep
):
    """
    Parse and analyze campaign brief.

    Extracts structured information from the brief using AI.
    """
    try:
        # Read brief content
        brief_content = await files.read_file(project_id, "brief-original.md")

        # Parse with AI
        result = await parser.parse_brief(project_id, brief_content)

        # Save expanded brief
        await parser.save_parsed_brief(project_id, result)

        logger.info(f"Parsed brief for project: {project_id}")

        return result
    except (ProjectNotFoundError, FileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found or brief not uploaded: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")


@router.post("/upload")
async def upload_brief(
    project_id: str,
    brief: BriefUpload,
    files: FileServiceDep,
    api_key: APIKeyDep
):
    """
    Upload campaign brief.

    Stores the brief content as markdown in the project.
    """
    try:
        path = await files.save_brief(project_id, brief.content)

        logger.info(f"Uploaded brief for project: {project_id}")

        return {
            "project_id": project_id,
            "file_path": str(path),
            "status": "uploaded"
        }
    except (ProjectNotFoundError, FileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")


@router.get("")
async def get_brief(project_id: str, files: FileServiceDep):
    """
    Get the original and parsed brief for a project.
    """
    try:
        original = await files.read_file(project_id, "brief-original.md")
    except (FileNotFoundError):
        original = None

    try:
        expanded = await files.read_file(project_id, "brief-expanded.md")
    except (FileNotFoundError):
        expanded = None

    if not original and not expanded:
        raise HTTPException(status_code=404, detail="No brief found for project")

    return {
        "project_id": project_id,
        "original": original,
        "expanded": expanded
    }
