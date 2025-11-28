"""
Message generation and management routes.

AI-powered personalized message generation using brand briefs.
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

from ..dependencies import APIKeyDep
from ..logging_config import get_logger
from ..models.outreach_models import (
    MessageGenerateRequest,
    MessageGenerateResponse,
    MessageResponse,
    MessageListResponse,
    MessageValidationResult,
    MessageTypeType,
    LanguageType,
)
from ..services.prospect_service import get_prospect_service
from ..services.brand_brief_loader import get_brand_brief_loader
from ..services.message_validator import get_message_validator

router = APIRouter(prefix="/messages", tags=["outreach-messages"])
logger = get_logger("routes.messages")


@router.post("/generate", response_model=MessageGenerateResponse)
async def generate_message(
    request: MessageGenerateRequest,
    api_key: APIKeyDep,
):
    """
    Generate a personalized outreach message.

    Uses AI to create a message based on:
    - Prospect's brand brief
    - Message type (connection_request, email_initial, etc.)
    - ICP type (solopreneur, sme, enterprise)
    - Target language (en, es, pt)

    The message goes through a brainstorm-critique-refine workflow
    to ensure quality and relevance.
    """
    try:
        # Get prospect data
        prospect_service = get_prospect_service()
        prospect = await prospect_service.get_prospect(request.prospect_id)

        if not prospect:
            raise HTTPException(
                status_code=404,
                detail=f"Prospect not found: {request.prospect_id}"
            )

        # Load brand brief
        brand_brief_loader = get_brand_brief_loader()
        brand_brief = None

        if prospect.get("brand_brief_path"):
            brand_brief = brand_brief_loader.load_brief(prospect["brand_brief_path"])

        if not brand_brief and request.require_brand_brief:
            raise HTTPException(
                status_code=400,
                detail="Brand brief required but not found for prospect"
            )

        # Import personalization agent
        from ..agents.personalization_agent import generate_personalized_message

        # Generate message
        result = await generate_personalized_message(
            brand_brief=brand_brief or {},
            prospect_name=prospect.get("first_name", ""),
            prospect_full_name=f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip(),
            prospect_role=prospect.get("role", ""),
            prospect_company=prospect.get("company", ""),
            message_type=request.message_type,
            icp_type=request.icp_type or brand_brief_loader.get_icp_type(brand_brief or {}),
            industry=prospect.get("industry", ""),
            language=request.language,
            max_iterations=request.max_iterations or 2,
        )

        # Validate generated message
        validator = get_message_validator()
        validation = validator.validate_message(
            message=result.get("message", ""),
            message_type=request.message_type,
            icp_type=request.icp_type or "sme",
            language=request.language,
            prospect_context={
                "first_name": prospect.get("first_name"),
                "company": prospect.get("company"),
                "role": prospect.get("role"),
                "industry": prospect.get("industry"),
            },
            subject=result.get("subject"),
        )

        logger.info(
            f"Generated {request.message_type} message for prospect {request.prospect_id} "
            f"(score: {validation['overall_score']:.2f})"
        )

        return MessageGenerateResponse(
            prospect_id=request.prospect_id,
            message_type=request.message_type,
            subject=result.get("subject"),
            message=result.get("message", ""),
            personalization_elements=result.get("personalization_elements", []),
            pillar_used=result.get("pillar_used", ""),
            validation_score=validation["overall_score"],
            validation_issues=validation.get("issues", []),
            iterations=result.get("iterations", 1),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating message: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate message: {str(e)}"
        )


@router.post("/generate/batch")
async def generate_messages_batch(
    campaign_id: int,
    message_type: MessageTypeType,
    language: LanguageType = "en",
    limit: int = Query(10, ge=1, le=50),
    background_tasks: BackgroundTasks = None,
    api_key: APIKeyDep = None,
):
    """
    Generate messages for multiple prospects in a campaign.

    Generates messages in the background and saves them to the database.
    Useful for preparing a batch of outreach messages before sending.
    """
    try:
        prospect_service = get_prospect_service()

        # Get prospects ready for messaging
        prospects = await prospect_service.get_prospects_for_messaging(
            campaign_id=campaign_id,
            message_type=message_type,
            limit=limit,
        )

        if not prospects:
            return {
                "status": "no_prospects",
                "message": "No prospects ready for message generation",
                "count": 0,
            }

        # Queue background generation
        async def generate_batch():
            from ..agents.personalization_agent import generate_personalized_message

            brand_brief_loader = get_brand_brief_loader()
            validator = get_message_validator()

            results = {"generated": 0, "failed": 0, "errors": []}

            for prospect in prospects:
                try:
                    brand_brief = None
                    if prospect.get("brand_brief_path"):
                        brand_brief = brand_brief_loader.load_brief(
                            prospect["brand_brief_path"]
                        )

                    result = await generate_personalized_message(
                        brand_brief=brand_brief or {},
                        prospect_name=prospect.get("first_name", ""),
                        prospect_full_name=f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip(),
                        prospect_role=prospect.get("role", ""),
                        prospect_company=prospect.get("company", ""),
                        message_type=message_type,
                        icp_type=brand_brief_loader.get_icp_type(brand_brief or {}),
                        industry=prospect.get("industry", ""),
                        language=language,
                    )

                    # Save to database
                    await prospect_service.save_generated_message(
                        prospect_id=prospect["id"],
                        campaign_id=campaign_id,
                        message_type=message_type,
                        subject=result.get("subject"),
                        content=result.get("message", ""),
                        personalization_data={
                            "elements": result.get("personalization_elements", []),
                            "pillar": result.get("pillar_used", ""),
                        },
                    )

                    results["generated"] += 1

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append(f"Prospect {prospect['id']}: {str(e)}")
                    logger.error(f"Error generating message for prospect {prospect['id']}: {e}")

            logger.info(
                f"Batch generation complete for campaign {campaign_id}: "
                f"{results['generated']} generated, {results['failed']} failed"
            )

        if background_tasks:
            background_tasks.add_task(generate_batch)

            return {
                "status": "queued",
                "message": f"Generating messages for {len(prospects)} prospects",
                "count": len(prospects),
            }
        else:
            await generate_batch()
            return {
                "status": "completed",
                "count": len(prospects),
            }

    except Exception as e:
        logger.error(f"Error in batch generation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start batch generation: {str(e)}"
        )


@router.post("/validate", response_model=MessageValidationResult)
async def validate_message(
    message: str,
    message_type: MessageTypeType,
    icp_type: str = "sme",
    language: LanguageType = "en",
    subject: str | None = None,
    prospect_context: dict | None = None,
):
    """
    Validate a message against quality criteria.

    Checks:
    - Length constraints
    - Tone matching for ICP
    - Cultural fit for language
    - Personalization depth
    - CTA presence
    """
    try:
        validator = get_message_validator()
        result = validator.validate_message(
            message=message,
            message_type=message_type,
            icp_type=icp_type,
            language=language,
            prospect_context=prospect_context or {},
            subject=subject,
        )

        return MessageValidationResult(**result)

    except Exception as e:
        logger.error(f"Error validating message: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {str(e)}"
        )


@router.get("", response_model=MessageListResponse)
async def list_messages(
    campaign_id: int | None = Query(None),
    prospect_id: int | None = Query(None),
    message_type: MessageTypeType | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """
    List messages with filtering.

    Can filter by campaign, prospect, type, and status.
    """
    try:
        prospect_service = get_prospect_service()
        result = await prospect_service.list_messages(
            campaign_id=campaign_id,
            prospect_id=prospect_id,
            message_type=message_type,
            status=status,
            skip=skip,
            limit=limit,
        )

        return MessageListResponse(
            messages=[MessageResponse(**m) for m in result["items"]],
            total=result["total"],
        )

    except Exception as e:
        logger.error(f"Error listing messages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(message_id: int):
    """
    Get message details.

    Returns full message data including engagement events.
    """
    try:
        prospect_service = get_prospect_service()
        message = await prospect_service.get_message(message_id)

        if not message:
            raise HTTPException(
                status_code=404,
                detail=f"Message not found: {message_id}"
            )

        return MessageResponse(**message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{message_id}")
async def update_message(
    message_id: int,
    content: str | None = None,
    subject: str | None = None,
    status: str | None = None,
    api_key: APIKeyDep = None,
):
    """
    Update a message.

    Can update content, subject, or status.
    Only draft/scheduled messages can have content updated.
    """
    try:
        prospect_service = get_prospect_service()

        update_data = {}
        if content is not None:
            update_data["content"] = content
        if subject is not None:
            update_data["subject"] = subject
        if status is not None:
            update_data["status"] = status

        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No update fields provided"
            )

        result = await prospect_service.update_message(message_id, update_data)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Message not found: {message_id}"
            )

        logger.info(f"Updated message: {message_id}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating message {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{message_id}", status_code=204)
async def delete_message(
    message_id: int,
    api_key: APIKeyDep,
):
    """
    Delete a message.

    Only draft/scheduled messages can be deleted.
    """
    try:
        prospect_service = get_prospect_service()
        deleted = await prospect_service.delete_message(message_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Message not found: {message_id}"
            )

        logger.info(f"Deleted message: {message_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting message {message_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/templates/list")
async def list_message_templates(
    message_type: MessageTypeType | None = Query(None),
    icp_type: str | None = Query(None),
    language: LanguageType | None = Query(None),
):
    """
    List available message templates.

    Templates are pre-built message structures that can be customized.
    """
    try:
        prospect_service = get_prospect_service()
        templates = await prospect_service.list_templates(
            message_type=message_type,
            icp_type=icp_type,
            language=language,
        )

        return {"templates": templates}

    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
