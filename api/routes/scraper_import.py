"""
Scraper Import Routes.

API endpoints for importing prospects from webscraper output.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from ..dependencies import APIKeyDep
from ..logging_config import get_logger
from ..database.engine import get_db_session
from ..services.scraper_import_service import ScraperImportService

router = APIRouter(prefix="/import", tags=["scraper-import"])
logger = get_logger("routes.scraper_import")


# =============================================================================
# Request Models
# =============================================================================


class ImportFromFileRequest(BaseModel):
    """Request to import from a file path."""

    file_path: str
    campaign_id: int | None = None
    skip_duplicates: bool = True
    auto_start_sequence: bool = False


class ImportFromDirectoryRequest(BaseModel):
    """Request to import from a directory."""

    directory_path: str
    campaign_id: int | None = None
    pattern: str = "*.json"
    skip_duplicates: bool = True


# =============================================================================
# Import Routes
# =============================================================================


@router.post("/scraper/file")
async def import_from_scraper_file(
    request: ImportFromFileRequest,
    api_key: APIKeyDep,
):
    """
    Import prospects from a single webscraper JSON output file.

    The scraper JSON should contain decision_makers with:
    - name
    - email
    - title
    - linkedin

    And company information with:
    - pain points from sentiment analysis
    - talking points
    - competitor analysis
    """
    try:
        async with get_db_session() as db:
            service = ScraperImportService(db)
            result = await service.import_from_json(
                json_path=request.file_path,
                campaign_id=request.campaign_id,
                skip_duplicates=request.skip_duplicates,
                auto_start_sequence=request.auto_start_sequence,
            )

            return {
                "status": "completed" if result["success"] else "failed",
                "file": request.file_path,
                "prospects_found": result["prospects_found"],
                "prospects_imported": result["prospects_imported"],
                "prospects_skipped": result["prospects_skipped"],
                "prospects_updated": result["prospects_updated"],
                "errors": result["errors"],
            }

    except Exception as e:
        logger.error(f"Error importing from file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scraper/directory")
async def import_from_scraper_directory(
    request: ImportFromDirectoryRequest,
    api_key: APIKeyDep,
):
    """
    Import prospects from all JSON files in a directory.

    Processes all files matching the pattern (default: *.json).
    """
    try:
        async with get_db_session() as db:
            service = ScraperImportService(db)
            result = await service.import_from_directory(
                directory_path=request.directory_path,
                campaign_id=request.campaign_id,
                pattern=request.pattern,
                skip_duplicates=request.skip_duplicates,
            )

            return {
                "status": "completed" if result["success"] else "failed",
                "directory": request.directory_path,
                "files_processed": result["files_processed"],
                "total_prospects_found": result["total_prospects_found"],
                "total_prospects_imported": result["total_prospects_imported"],
                "total_prospects_skipped": result["total_prospects_skipped"],
                "file_results": result["file_results"],
                "errors": result["errors"],
            }

    except Exception as e:
        logger.error(f"Error importing from directory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scraper/upload")
async def import_from_uploaded_file(
    file: UploadFile = File(...),
    campaign_id: int | None = Query(None),
    skip_duplicates: bool = Query(True),
    api_key: APIKeyDep = None,
):
    """
    Import prospects from an uploaded JSON file.

    Upload the webscraper JSON output directly.
    """
    try:
        # Read uploaded file
        content = await file.read()

        # Save to temp location
        import tempfile
        import json

        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".json",
            delete=False,
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # Import from temp file
        async with get_db_session() as db:
            service = ScraperImportService(db)
            result = await service.import_from_json(
                json_path=tmp_path,
                campaign_id=campaign_id,
                skip_duplicates=skip_duplicates,
            )

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        return {
            "status": "completed" if result["success"] else "failed",
            "filename": file.filename,
            "prospects_found": result["prospects_found"],
            "prospects_imported": result["prospects_imported"],
            "prospects_skipped": result["prospects_skipped"],
            "errors": result["errors"],
        }

    except Exception as e:
        logger.error(f"Error importing uploaded file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Preview Routes
# =============================================================================


@router.post("/scraper/preview")
async def preview_scraper_import(
    request: ImportFromFileRequest,
):
    """
    Preview what would be imported from a scraper file.

    Does not actually import - just shows what would be extracted.
    """
    try:
        import json

        path = Path(request.file_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Extract prospects without importing
        async with get_db_session() as db:
            service = ScraperImportService(db)
            prospects_data = service._extract_prospects(data)

        return {
            "file": request.file_path,
            "prospects_found": len(prospects_data),
            "preview": [
                {
                    "email": p.get("email"),
                    "name": f"{p.get('first_name', '')} {p.get('last_name', '')}",
                    "title": p.get("title"),
                    "company": p.get("company"),
                    "priority": p.get("priority_tier"),
                    "pain_points_count": len(
                        p.get("personalization_data", {}).get("pain_points", [])
                    ),
                }
                for p in prospects_data[:10]  # Show first 10
            ],
            "has_more": len(prospects_data) > 10,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error previewing import: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Status Routes
# =============================================================================


@router.get("/history")
async def get_import_history(
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get recent import history.

    Shows past imports with stats and status.
    """
    # This would query the scraper_imports table
    return {
        "imports": [],
        "message": "Import history tracking not yet implemented",
    }


@router.get("/scraper/output-path")
async def get_default_scraper_path():
    """
    Get the default webscraper output path.

    Returns the expected location of scraper JSON files.
    """
    default_path = Path("../company-webscraper/output")

    return {
        "default_path": str(default_path.absolute()),
        "exists": default_path.exists(),
        "json_files": (
            len(list(default_path.glob("*.json")))
            if default_path.exists()
            else 0
        ),
    }
