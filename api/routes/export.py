"""
Export routes for PDF and PowerPoint generation.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..dependencies import APIKeyDep, ExportServiceDep, FileServiceDep
from ..exceptions import FileNotFoundError, ProjectNotFoundError
from ..logging_config import get_logger
from ..models import ExportRequest
from ..security import validate_filename, validate_project_id

router = APIRouter(prefix="/projects/{project_id}/export", tags=["export"])
logger = get_logger("routes.export")


@router.post("/pdf")
async def export_pdf(
    project_id: str,
    files: FileServiceDep,
    export: ExportServiceDep,
    api_key: APIKeyDep,
    request: ExportRequest = None
):
    """
    Export project to PDF.

    Creates a PDF document with selected content.
    """
    if request is None:
        request = ExportRequest()

    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, FileNotFoundError):
        raise HTTPException(
            status_code=404,
            detail=f"Project not found: {project_id}"
        )
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    # Export
    pdf_path = await export.export_to_pdf(
        project_id=project_id,
        include_sections=request.include_sections
    )

    logger.info(f"Exported PDF for project: {project_id}")

    return FileResponse(
        path=pdf_path,
        filename=f"{project_id}.pdf",
        media_type="application/pdf"
    )


@router.post("/pptx")
async def export_pptx(
    project_id: str,
    files: FileServiceDep,
    export: ExportServiceDep,
    api_key: APIKeyDep,
    request: ExportRequest = None
):
    """
    Export project to PowerPoint.

    Creates a PPTX presentation with selected content.
    """
    if request is None:
        request = ExportRequest()

    # Verify project exists
    try:
        files.get_project_path(project_id)
    except (ProjectNotFoundError, FileNotFoundError):
        raise HTTPException(
            status_code=404,
            detail=f"Project not found: {project_id}"
        )
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    # Export
    pptx_path = await export.export_to_pptx(
        project_id=project_id,
        include_sections=request.include_sections
    )

    logger.info(f"Exported PPTX for project: {project_id}")

    return FileResponse(
        path=pptx_path,
        filename=f"{project_id}.pptx",
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


@router.get("")
async def list_exports(project_id: str, files: FileServiceDep):
    """
    List all exports for a project.
    """
    files = get_file_service()

    try:
        export_files = files.list_files(project_id, "exports", "*")
    except (ProjectNotFoundError, CustomFileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied listing exports for project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    return {
        "project_id": project_id,
        "exports": export_files,
        "count": len(export_files)
    }


@router.get("/download/{filename}")
async def download_export(project_id: str, filename: str):
    """
    Download an export file.
    """
    # Validate inputs to prevent path traversal attacks
    validate_project_id(project_id)
    validate_filename(filename)

    files = get_file_service()

    try:
        project_path = files.get_project_path(project_id)
    except (ProjectNotFoundError, CustomFileNotFoundError):
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    except PermissionError as e:
        logger.error(f"Permission denied accessing project {project_id}: {e}")
        raise HTTPException(status_code=403, detail="Permission denied")

    file_path = project_path / "exports" / filename

    # Additional security check: ensure file is within exports directory
    try:
        resolved_path = file_path.resolve()
        exports_dir = (project_path / "exports").resolve()
        if not str(resolved_path).startswith(str(exports_dir)):
            logger.warning(f"Path traversal attempt: {filename} -> {resolved_path}")
            raise HTTPException(status_code=400, detail="Invalid filename")
    except OSError as e:
        logger.error(f"Error resolving path for {filename}: {e}")
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Export not found: {filename}")

    # Determine media type
    media_type = "application/octet-stream"
    if filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif filename.endswith(".pptx"):
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename
    )
