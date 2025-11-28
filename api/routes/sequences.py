"""
Sequence Management Routes.

API endpoints for managing email sequences and follow-up scheduling.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..dependencies import APIKeyDep
from ..logging_config import get_logger
from ..database.engine import get_db_session
from ..services.sequence_service import (
    SequenceService,
    SequenceConfig,
    SequenceStep,
    DEFAULT_SEQUENCES,
)

router = APIRouter(prefix="/sequences", tags=["sequences"])
logger = get_logger("routes.sequences")


# =============================================================================
# Request/Response Models
# =============================================================================


class SequenceStepCreate(BaseModel):
    """Step definition for sequence creation."""

    step_number: int
    delay_days: int
    delay_hours: int = 0
    message_type: str
    template_id: int | None = None
    skip_if_opened: bool = False
    skip_if_clicked: bool = False


class SequenceCreate(BaseModel):
    """Request model for creating a sequence."""

    name: str
    description: str | None = None
    steps: list[SequenceStepCreate]


class SequenceResponse(BaseModel):
    """Response model for sequence data."""

    name: str
    description: str | None
    steps: list[dict]
    is_active: bool = True
    total_steps: int
    total_days: int


class ProspectSequenceStart(BaseModel):
    """Request to start sequence for a prospect."""

    prospect_id: int
    sequence_name: str = "standard"


class ProspectSequenceAction(BaseModel):
    """Request for sequence actions (pause/resume)."""

    prospect_id: int
    reason: str | None = None


# =============================================================================
# Sequence CRUD Routes
# =============================================================================


@router.get("", response_model=list[SequenceResponse])
async def list_sequences():
    """
    List all available sequences.

    Returns both default and custom sequences.
    """
    try:
        async with get_db_session() as db:
            service = SequenceService(db)
            configs = await service.list_sequences()

            sequences = []
            for config in configs:
                total_days = sum(step.delay_days for step in config.steps)
                sequences.append(SequenceResponse(
                    name=config.name,
                    description=config.description,
                    steps=[step.model_dump() for step in config.steps],
                    is_active=config.is_active,
                    total_steps=len(config.steps),
                    total_days=total_days,
                ))

            return sequences

    except Exception as e:
        logger.error(f"Error listing sequences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sequence_name}", response_model=SequenceResponse)
async def get_sequence(sequence_name: str):
    """
    Get a specific sequence by name.

    Available default sequences: standard, aggressive, gentle
    Custom sequences can be created via POST /sequences
    """
    try:
        async with get_db_session() as db:
            service = SequenceService(db)
            config = await service.get_sequence(sequence_name)

            if not config:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sequence not found: {sequence_name}"
                )

            total_days = sum(step.delay_days for step in config.steps)

            return SequenceResponse(
                name=config.name,
                description=config.description,
                steps=[step.model_dump() for step in config.steps],
                is_active=config.is_active,
                total_steps=len(config.steps),
                total_days=total_days,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sequence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=SequenceResponse)
async def create_sequence(
    sequence: SequenceCreate,
    api_key: APIKeyDep,
):
    """
    Create a custom sequence.

    Custom sequences allow different timing and skip conditions.
    """
    try:
        # Validate sequence
        if not sequence.steps:
            raise HTTPException(
                status_code=400,
                detail="Sequence must have at least one step"
            )

        # Build config
        steps = [
            SequenceStep(**step.model_dump())
            for step in sequence.steps
        ]

        config = SequenceConfig(
            name=sequence.name,
            description=sequence.description,
            steps=steps,
        )

        # Save to database
        async with get_db_session() as db:
            service = SequenceService(db)
            try:
                db_sequence = await service.create_sequence(config)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        total_days = sum(step.delay_days for step in steps)

        logger.info(f"Created sequence: {sequence.name}")

        return SequenceResponse(
            name=config.name,
            description=config.description,
            steps=[step.model_dump() for step in config.steps],
            is_active=True,
            total_steps=len(config.steps),
            total_days=total_days,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating sequence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{sequence_name}", response_model=SequenceResponse)
async def update_sequence(
    sequence_name: str,
    sequence: SequenceCreate,
    api_key: APIKeyDep,
):
    """
    Update a custom sequence.

    Note: Default sequences (standard, aggressive, gentle) cannot be modified.
    """
    try:
        # Build config
        steps = [
            SequenceStep(**step.model_dump())
            for step in sequence.steps
        ]

        config = SequenceConfig(
            name=sequence.name,
            description=sequence.description,
            steps=steps,
        )

        async with get_db_session() as db:
            service = SequenceService(db)
            try:
                db_sequence = await service.update_sequence(sequence_name, config)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            if not db_sequence:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sequence not found: {sequence_name}"
                )

        total_days = sum(step.delay_days for step in steps)

        return SequenceResponse(
            name=config.name,
            description=config.description,
            steps=[step.model_dump() for step in config.steps],
            is_active=True,
            total_steps=len(config.steps),
            total_days=total_days,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating sequence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{sequence_name}")
async def delete_sequence(
    sequence_name: str,
    api_key: APIKeyDep,
):
    """
    Delete a custom sequence.

    Note: Default sequences (standard, aggressive, gentle) cannot be deleted.
    This is a soft delete - the sequence is deactivated but retained in the database.
    """
    try:
        async with get_db_session() as db:
            service = SequenceService(db)
            try:
                success = await service.delete_sequence(sequence_name)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            if not success:
                raise HTTPException(
                    status_code=404,
                    detail=f"Sequence not found: {sequence_name}"
                )

            return {"status": "deleted", "sequence_name": sequence_name}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting sequence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Prospect Sequence Management
# =============================================================================


@router.post("/start")
async def start_prospect_sequence(
    request: ProspectSequenceStart,
    api_key: APIKeyDep,
):
    """
    Start a sequence for a prospect.

    Initializes sequence tracking and schedules the first message.
    """
    try:
        async with get_db_session() as db:
            service = SequenceService(db)
            result = await service.start_sequence(
                prospect_id=request.prospect_id,
                sequence_name=request.sequence_name,
            )

            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])

            return {
                "status": "started",
                **result,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting sequence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause")
async def pause_prospect_sequence(
    request: ProspectSequenceAction,
    api_key: APIKeyDep,
):
    """
    Pause a prospect's sequence.

    Stops sending follow-ups until resumed.
    """
    try:
        async with get_db_session() as db:
            service = SequenceService(db)
            success = await service.pause_sequence(
                prospect_id=request.prospect_id,
                reason=request.reason or "Manual pause",
            )

            return {
                "status": "paused" if success else "failed",
                "prospect_id": request.prospect_id,
            }

    except Exception as e:
        logger.error(f"Error pausing sequence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume")
async def resume_prospect_sequence(
    request: ProspectSequenceAction,
    api_key: APIKeyDep,
):
    """
    Resume a paused sequence.

    Re-enables follow-up sending for the prospect.
    """
    try:
        async with get_db_session() as db:
            service = SequenceService(db)
            success = await service.resume_sequence(
                prospect_id=request.prospect_id,
            )

            return {
                "status": "resumed" if success else "failed",
                "prospect_id": request.prospect_id,
            }

    except Exception as e:
        logger.error(f"Error resuming sequence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Follow-up Management
# =============================================================================


@router.get("/due")
async def get_due_followups(
    campaign_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
):
    """
    Get prospects due for follow-up.

    Returns prospects whose next_followup_at has passed.
    """
    try:
        async with get_db_session() as db:
            service = SequenceService(db)
            prospects = await service.get_prospects_due_for_followup(
                campaign_id=campaign_id,
                limit=limit,
            )

            return {
                "count": len(prospects),
                "prospects": [
                    {
                        "id": p.id,
                        "email": p.email,
                        "company": p.company,
                        "current_step": p.current_sequence_step,
                        "next_followup_at": p.next_followup_at,
                    }
                    for p in prospects
                ],
            }

    except Exception as e:
        logger.error(f"Error getting due follow-ups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schedule-next/{prospect_id}")
async def schedule_next_followup(
    prospect_id: int,
    api_key: APIKeyDep,
):
    """
    Schedule the next follow-up for a specific prospect.

    Calculates timing and creates the scheduled message.
    """
    try:
        async with get_db_session() as db:
            service = SequenceService(db)

            # Get prospect
            from sqlalchemy import select
            from ..database.outreach_models import Prospect

            stmt = select(Prospect).where(Prospect.id == prospect_id)
            result = await db.execute(stmt)
            prospect = result.scalar_one_or_none()

            if not prospect:
                raise HTTPException(status_code=404, detail="Prospect not found")

            schedule_result = await service.schedule_next_followup(prospect)

            return schedule_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling follow-up: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Utility Routes
# =============================================================================


@router.get("/strategies")
async def get_followup_strategies():
    """
    Get follow-up message strategies.

    Returns the recommended approach for each follow-up step.
    """
    from ..services.sequence_service import FOLLOWUP_STRATEGIES

    return {
        "strategies": FOLLOWUP_STRATEGIES,
        "description": "Each follow-up uses a different angle to maintain interest",
    }
