"""
Prospect management routes.

CRUD operations and bulk import for outreach prospects.
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form

from ..dependencies import APIKeyDep
from ..logging_config import get_logger
from ..models.outreach_models import (
    ProspectCreate,
    ProspectResponse,
    ProspectUpdate,
    ProspectListResponse,
    ProspectImportResult,
    ProspectStatusType,
)
from ..services.prospect_service import get_prospect_service

router = APIRouter(prefix="/prospects", tags=["outreach-prospects"])
logger = get_logger("routes.prospects")


@router.post("", response_model=ProspectResponse, status_code=201)
async def create_prospect(
    prospect: ProspectCreate,
    api_key: APIKeyDep,
):
    """
    Create a single prospect.

    Associates prospect with a campaign and optionally links to brand brief.
    """
    try:
        prospect_service = get_prospect_service()
        result = await prospect_service.create_prospect(
            campaign_id=prospect.campaign_id,
            first_name=prospect.first_name,
            last_name=prospect.last_name,
            email=prospect.email,
            linkedin_url=prospect.linkedin_url,
            company=prospect.company,
            role=prospect.role,
            industry=prospect.industry,
            company_size=prospect.company_size,
            location=prospect.location,
            brand_brief_path=prospect.brand_brief_path,
            custom_data=prospect.custom_data,
        )

        logger.info(f"Created prospect: {result['id']} - {prospect.first_name} {prospect.last_name}")

        return ProspectResponse(**result)

    except Exception as e:
        logger.error(f"Error creating prospect: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create prospect: {str(e)}"
        )


@router.post("/import/csv", response_model=ProspectImportResult)
async def import_prospects_csv(
    campaign_id: int = Form(...),
    file: UploadFile = File(...),
    skip_duplicates: bool = Form(True),
    auto_link_brand_briefs: bool = Form(True),
    api_key: APIKeyDep = None,
):
    """
    Import prospects from CSV file.

    Expected CSV columns:
    - first_name, last_name (required)
    - email, linkedin_url (at least one required)
    - company, role, industry, company_size, location (optional)
    - brand_brief_path (optional - for linking to brand brief files)

    Options:
    - skip_duplicates: Skip rows with existing email/linkedin (default: true)
    - auto_link_brand_briefs: Match company names to brand brief folders (default: true)
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="File must be a CSV file"
        )

    try:
        # Read CSV content
        content = await file.read()
        csv_content = content.decode('utf-8')

        prospect_service = get_prospect_service()
        result = await prospect_service.import_from_csv(
            campaign_id=campaign_id,
            csv_content=csv_content,
            skip_duplicates=skip_duplicates,
            auto_link_brand_briefs=auto_link_brand_briefs,
        )

        logger.info(
            f"Imported prospects to campaign {campaign_id}: "
            f"{result['imported']} imported, {result['skipped']} skipped, "
            f"{result['errors']} errors"
        )

        return ProspectImportResult(**result)

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="CSV file encoding error. Please use UTF-8 encoding."
        )
    except Exception as e:
        logger.error(f"Error importing CSV: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import CSV: {str(e)}"
        )


@router.post("/import/json", response_model=ProspectImportResult)
async def import_prospects_json(
    campaign_id: int = Form(...),
    file: UploadFile = File(...),
    skip_duplicates: bool = Form(True),
    auto_link_brand_briefs: bool = Form(True),
    api_key: APIKeyDep = None,
):
    """
    Import prospects from JSON file.

    Expected JSON format:
    [
        {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "linkedin_url": "https://linkedin.com/in/johndoe",
            "company": "Acme Corp",
            "role": "CEO",
            ...
        }
    ]
    """
    if not file.filename.endswith('.json'):
        raise HTTPException(
            status_code=400,
            detail="File must be a JSON file"
        )

    try:
        import json

        content = await file.read()
        prospects_data = json.loads(content.decode('utf-8'))

        if not isinstance(prospects_data, list):
            raise HTTPException(
                status_code=400,
                detail="JSON must be an array of prospect objects"
            )

        prospect_service = get_prospect_service()
        result = await prospect_service.import_from_json(
            campaign_id=campaign_id,
            prospects_data=prospects_data,
            skip_duplicates=skip_duplicates,
            auto_link_brand_briefs=auto_link_brand_briefs,
        )

        logger.info(
            f"Imported prospects from JSON to campaign {campaign_id}: "
            f"{result['imported']} imported, {result['skipped']} skipped"
        )

        return ProspectImportResult(**result)

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error importing JSON: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import JSON: {str(e)}"
        )


@router.get("", response_model=ProspectListResponse)
async def list_prospects(
    campaign_id: int | None = Query(None, description="Filter by campaign"),
    status: ProspectStatusType | None = Query(None, description="Filter by status"),
    company: str | None = Query(None, description="Filter by company name"),
    search: str | None = Query(None, description="Search name/email/company"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """
    List prospects with filtering and pagination.

    Supports filtering by campaign, status, company, and text search.
    """
    try:
        prospect_service = get_prospect_service()
        result = await prospect_service.list_prospects(
            campaign_id=campaign_id,
            status=status,
            company=company,
            search=search,
            skip=skip,
            limit=limit,
        )

        return ProspectListResponse(
            prospects=[ProspectResponse(**p) for p in result["items"]],
            total=result["total"],
        )

    except Exception as e:
        logger.error(f"Error listing prospects: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{prospect_id}", response_model=ProspectResponse)
async def get_prospect(prospect_id: int):
    """
    Get prospect details.

    Returns full prospect data including outreach history.
    """
    try:
        prospect_service = get_prospect_service()
        prospect = await prospect_service.get_prospect(prospect_id)

        if not prospect:
            raise HTTPException(
                status_code=404,
                detail=f"Prospect not found: {prospect_id}"
            )

        return ProspectResponse(**prospect)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting prospect {prospect_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{prospect_id}", response_model=ProspectResponse)
async def update_prospect(
    prospect_id: int,
    update: ProspectUpdate,
    api_key: APIKeyDep,
):
    """
    Update prospect data.

    Can update contact info, status, and custom data.
    """
    try:
        prospect_service = get_prospect_service()

        update_data = update.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No update fields provided"
            )

        result = await prospect_service.update_prospect(prospect_id, update_data)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Prospect not found: {prospect_id}"
            )

        logger.info(f"Updated prospect: {prospect_id}")

        return ProspectResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating prospect {prospect_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{prospect_id}", status_code=204)
async def delete_prospect(
    prospect_id: int,
    api_key: APIKeyDep,
):
    """
    Delete a prospect.

    Also deletes all associated messages and engagement events.
    """
    try:
        prospect_service = get_prospect_service()
        deleted = await prospect_service.delete_prospect(prospect_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Prospect not found: {prospect_id}"
            )

        logger.info(f"Deleted prospect: {prospect_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting prospect {prospect_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{prospect_id}/link-brief", response_model=ProspectResponse)
async def link_brand_brief(
    prospect_id: int,
    brand_brief_path: str = Form(...),
    api_key: APIKeyDep = None,
):
    """
    Link a prospect to a brand brief file.

    The brand brief provides context for personalized message generation.
    """
    try:
        prospect_service = get_prospect_service()
        result = await prospect_service.link_brand_brief(
            prospect_id=prospect_id,
            brand_brief_path=brand_brief_path,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Prospect not found: {prospect_id}"
            )

        logger.info(f"Linked brand brief to prospect {prospect_id}: {brand_brief_path}")

        return ProspectResponse(**result)

    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"Brand brief file not found: {brand_brief_path}"
        )
    except Exception as e:
        logger.error(f"Error linking brand brief to prospect {prospect_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk/update-status")
async def bulk_update_status(
    prospect_ids: list[int],
    status: ProspectStatusType,
    api_key: APIKeyDep,
):
    """
    Bulk update prospect status.

    Useful for marking prospects as opted out, bounced, etc.
    """
    try:
        prospect_service = get_prospect_service()
        result = await prospect_service.bulk_update_status(
            prospect_ids=prospect_ids,
            status=status,
        )

        logger.info(f"Bulk updated {result['updated']} prospects to status: {status}")

        return result

    except Exception as e:
        logger.error(f"Error bulk updating prospect status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{prospect_id}/messages")
async def get_prospect_messages(
    prospect_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
):
    """
    Get all messages sent to a prospect.

    Includes status and engagement events for each message.
    """
    try:
        prospect_service = get_prospect_service()
        result = await prospect_service.get_prospect_messages(
            prospect_id=prospect_id,
            skip=skip,
            limit=limit,
        )

        if result is None:
            raise HTTPException(
                status_code=404,
                detail=f"Prospect not found: {prospect_id}"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages for prospect {prospect_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
