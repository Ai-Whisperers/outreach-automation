"""
Project management routes.
"""

from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ..dependencies import APIKeyDep, FileServiceDep
from ..exceptions import ProjectExistsError, ProjectNotFoundError
from ..logging_config import get_logger
from ..models import ProjectCreate, ProjectListResponse, ProjectResponse

router = APIRouter(prefix="/projects", tags=["projects"])
logger = get_logger("routes.projects")


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    project: ProjectCreate,
    files: FileServiceDep,
    api_key: APIKeyDep
):
    """
    Create a new campaign project.

    Creates project directory structure and initializes metadata.
    """
    try:
        result = await files.create_project_structure(
            project_id=str(uuid4()),
            project_name=project.name,
            client=project.client,
            country=project.country,
            language=project.language,
            campaign_type=project.campaign_type
        )

        logger.info(f"Created project: {result['id']}")

        return ProjectResponse(**result)

    except ProjectExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"Project with name '{project.name}' already exists"
        )
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during project creation"
        )


@router.get("", response_model=ProjectListResponse)
async def list_projects(files: FileServiceDep):
    """
    List all projects.

    Returns metadata for all projects in the system.
    """
    try:
        projects = files.list_projects()

        return ProjectListResponse(
            projects=[ProjectResponse(**p) for p in projects],
            total=len(projects)
        )
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    files: FileServiceDep
):
    """
    Get project details.

    Returns metadata for a specific project.
    """
    try:
        metadata = files.get_project_metadata(project_id)
        return ProjectResponse(**metadata)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")
    except OSError as e:
        logger.error(f"OS error accessing project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    files: FileServiceDep,
    api_key: APIKeyDep
):
    """
    Delete a project.

    Removes project directory and all associated files.
    """
    try:
        files.delete_project(project_id)
        logger.info(f"Deleted project: {project_id}")
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied deleting project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")
    except OSError as e:
        logger.error(f"OS error deleting project {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    logger.info(f"Deleted project: {project_id}")

    return {"status": "deleted", "project_id": project_id}
