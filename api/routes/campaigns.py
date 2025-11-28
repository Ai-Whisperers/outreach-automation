"""
Outreach Campaign management routes.

CRUD operations for outreach campaigns.
"""

from fastapi import APIRouter, HTTPException, Query

from ..dependencies import APIKeyDep
from ..logging_config import get_logger
from ..models.outreach_models import (
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    CampaignListResponse,
    CampaignAnalytics,
)
from ..services.prospect_service import get_prospect_service

router = APIRouter(prefix="/campaigns", tags=["outreach-campaigns"])
logger = get_logger("routes.campaigns")


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    campaign: CampaignCreate,
    api_key: APIKeyDep,
):
    """
    Create a new outreach campaign.

    Campaigns group prospects and define outreach parameters:
    - Target ICP (solopreneur, sme, enterprise)
    - Channels (linkedin, email, both)
    - Timing and quotas
    """
    try:
        prospect_service = get_prospect_service()
        result = await prospect_service.create_campaign(
            name=campaign.name,
            description=campaign.description,
            icp_type=campaign.icp_type,
            target_channels=campaign.target_channels,
            daily_linkedin_limit=campaign.daily_linkedin_limit,
            daily_email_limit=campaign.daily_email_limit,
        )

        logger.info(f"Created campaign: {result['id']} - {campaign.name}")

        return CampaignResponse(**result)

    except Exception as e:
        logger.error(f"Error creating campaign: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create campaign: {str(e)}"
        )


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    status: str | None = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """
    List all outreach campaigns.

    Supports filtering by status and pagination.
    """
    try:
        prospect_service = get_prospect_service()
        campaigns = await prospect_service.list_campaigns(
            status=status,
            skip=skip,
            limit=limit,
        )

        return CampaignListResponse(
            campaigns=[CampaignResponse(**c) for c in campaigns["items"]],
            total=campaigns["total"],
        )

    except Exception as e:
        logger.error(f"Error listing campaigns: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: int):
    """
    Get campaign details.

    Returns full campaign metadata and current status.
    """
    try:
        prospect_service = get_prospect_service()
        campaign = await prospect_service.get_campaign(campaign_id)

        if not campaign:
            raise HTTPException(
                status_code=404,
                detail=f"Campaign not found: {campaign_id}"
            )

        return CampaignResponse(**campaign)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    update: CampaignUpdate,
    api_key: APIKeyDep,
):
    """
    Update campaign settings.

    Can update name, description, limits, and status.
    """
    try:
        prospect_service = get_prospect_service()

        # Build update dict from non-None values
        update_data = update.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No update fields provided"
            )

        result = await prospect_service.update_campaign(campaign_id, update_data)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Campaign not found: {campaign_id}"
            )

        logger.info(f"Updated campaign: {campaign_id}")

        return CampaignResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: int,
    api_key: APIKeyDep,
):
    """
    Delete a campaign.

    Also deletes all associated prospects and messages.
    Use with caution.
    """
    try:
        prospect_service = get_prospect_service()
        deleted = await prospect_service.delete_campaign(campaign_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Campaign not found: {campaign_id}"
            )

        logger.info(f"Deleted campaign: {campaign_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{campaign_id}/analytics", response_model=CampaignAnalytics)
async def get_campaign_analytics(campaign_id: int):
    """
    Get campaign analytics.

    Returns detailed stats on outreach performance:
    - Messages sent/opened/clicked/replied
    - Connection rates
    - Response rates by channel
    """
    try:
        prospect_service = get_prospect_service()
        analytics = await prospect_service.get_campaign_analytics(campaign_id)

        if not analytics:
            raise HTTPException(
                status_code=404,
                detail=f"Campaign not found: {campaign_id}"
            )

        return CampaignAnalytics(**analytics)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analytics for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{campaign_id}/activate", response_model=CampaignResponse)
async def activate_campaign(
    campaign_id: int,
    api_key: APIKeyDep,
):
    """
    Activate a campaign for outreach.

    Campaign must have prospects and valid configuration.
    Once active, daily batches will be scheduled automatically.
    """
    try:
        prospect_service = get_prospect_service()
        result = await prospect_service.activate_campaign(campaign_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Campaign not found: {campaign_id}"
            )

        if result.get("error"):
            raise HTTPException(
                status_code=400,
                detail=result["error"]
            )

        logger.info(f"Activated campaign: {campaign_id}")

        return CampaignResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    campaign_id: int,
    api_key: APIKeyDep,
):
    """
    Pause an active campaign.

    Scheduled messages will not be sent while paused.
    Can be reactivated later.
    """
    try:
        prospect_service = get_prospect_service()
        result = await prospect_service.pause_campaign(campaign_id)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Campaign not found: {campaign_id}"
            )

        logger.info(f"Paused campaign: {campaign_id}")

        return CampaignResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
