"""
Sequence Service.

Manages configurable email sequences with engagement-based follow-up logic.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.outreach_models import (
    MessageStatus,
    MessageType,
    OutreachCampaign,
    OutreachMessage,
    Prospect,
    ProspectStatus,
    Sequence,
)
from ..logging_config import get_logger

logger = get_logger("services.sequence")


# =============================================================================
# Models
# =============================================================================


class SequenceStep(BaseModel):
    """Single step in an email sequence."""

    step_number: int
    delay_days: int
    delay_hours: int = 0
    message_type: str  # MessageType value
    template_id: int | None = None
    skip_if_opened: bool = False
    skip_if_clicked: bool = False
    skip_if_replied: bool = True  # Always true effectively


class SequenceConfig(BaseModel):
    """Complete sequence configuration."""

    name: str
    description: str | None = None
    steps: list[SequenceStep]
    is_active: bool = True


class FollowUpDecision(BaseModel):
    """Decision about whether to send a follow-up."""

    should_send: bool
    reason: str
    adjust_tone: str | None = None
    skip_to_step: int | None = None
    delay_hours: int = 0  # Additional delay


# =============================================================================
# Pre-defined Sequences
# =============================================================================


STANDARD_SEQUENCE = SequenceConfig(
    name="standard",
    description="Standard 5-email sequence over 14 days",
    steps=[
        SequenceStep(step_number=1, delay_days=0, delay_hours=0, message_type="email_initial"),
        SequenceStep(step_number=2, delay_days=3, delay_hours=0, message_type="email_followup_1"),
        SequenceStep(step_number=3, delay_days=5, delay_hours=0, message_type="email_followup_2"),
        SequenceStep(step_number=4, delay_days=7, delay_hours=0, message_type="email_followup_3"),
        SequenceStep(step_number=5, delay_days=10, delay_hours=0, message_type="email_followup_4"),
    ],
)

AGGRESSIVE_SEQUENCE = SequenceConfig(
    name="aggressive",
    description="Aggressive 5-email sequence over 7 days for high-priority",
    steps=[
        SequenceStep(step_number=1, delay_days=0, delay_hours=0, message_type="email_initial"),
        SequenceStep(step_number=2, delay_days=1, delay_hours=0, message_type="email_followup_1"),
        SequenceStep(step_number=3, delay_days=2, delay_hours=0, message_type="email_followup_2"),
        SequenceStep(step_number=4, delay_days=3, delay_hours=0, message_type="email_followup_3"),
        SequenceStep(step_number=5, delay_days=5, delay_hours=0, message_type="email_followup_4"),
    ],
)

GENTLE_SEQUENCE = SequenceConfig(
    name="gentle",
    description="Gentle 4-email sequence over 21 days for nurture",
    steps=[
        SequenceStep(step_number=1, delay_days=0, delay_hours=0, message_type="email_initial"),
        SequenceStep(step_number=2, delay_days=7, delay_hours=0, message_type="email_followup_1"),
        SequenceStep(step_number=3, delay_days=14, delay_hours=0, message_type="email_followup_2"),
        SequenceStep(step_number=4, delay_days=21, delay_hours=0, message_type="email_followup_3"),
    ],
)

DEFAULT_SEQUENCES = {
    "standard": STANDARD_SEQUENCE,
    "aggressive": AGGRESSIVE_SEQUENCE,
    "gentle": GENTLE_SEQUENCE,
}


# =============================================================================
# Follow-up Strategies (for message variation)
# =============================================================================


FOLLOWUP_STRATEGIES = {
    1: {
        "angle": "gentle_reminder",
        "tone": "casual",
        "hook": "reference_previous_email",
        "length": "shorter",
        "cta": "soft_question",
    },
    2: {
        "angle": "new_value_prop",
        "tone": "helpful",
        "hook": "share_resource_or_insight",
        "length": "medium",
        "cta": "offer_value",
    },
    3: {
        "angle": "social_proof",
        "tone": "confident",
        "hook": "case_study_or_result",
        "length": "short",
        "cta": "specific_ask",
    },
    4: {
        "angle": "breakup",
        "tone": "respectful",
        "hook": "acknowledge_busy",
        "length": "very_short",
        "cta": "close_loop",
    },
}


# =============================================================================
# Sequence Service
# =============================================================================


class SequenceService:
    """
    Manage email sequences and follow-up scheduling.

    Features:
    - Configurable sequences (standard, aggressive, gentle, custom)
    - Engagement-based follow-up decisions
    - Smart scheduling with business hours awareness
    - Sequence pausing and resuming
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # =========================================================================
    # Sequence Management
    # =========================================================================

    async def get_sequence(self, sequence_name: str) -> SequenceConfig | None:
        """Get sequence by name (from DB or defaults)."""
        # First check defaults
        if sequence_name in DEFAULT_SEQUENCES:
            return DEFAULT_SEQUENCES.get(sequence_name)

        # Check database for custom sequences
        stmt = select(Sequence).where(
            Sequence.name == sequence_name,
            Sequence.is_active == True,
        )
        result = await self.db.execute(stmt)
        db_sequence = result.scalar_one_or_none()

        if db_sequence:
            # Convert DB model to SequenceConfig
            steps = [
                SequenceStep(**step) for step in (db_sequence.steps or [])
            ]
            return SequenceConfig(
                name=db_sequence.name,
                description=db_sequence.description,
                steps=steps,
                is_active=db_sequence.is_active,
            )

        return None

    async def get_campaign_sequence(self, campaign_id: int) -> SequenceConfig:
        """Get the sequence configured for a campaign."""
        stmt = select(OutreachCampaign).where(OutreachCampaign.id == campaign_id)
        result = await self.db.execute(stmt)
        campaign = result.scalar_one_or_none()

        if not campaign:
            return STANDARD_SEQUENCE

        # Check if campaign has custom sequence config
        if campaign.sequence_config:
            try:
                return SequenceConfig(**campaign.sequence_config)
            except Exception:
                pass

        # Use default standard sequence
        return STANDARD_SEQUENCE

    async def list_sequences(self) -> list[SequenceConfig]:
        """List all available sequences (defaults + custom from DB)."""
        sequences = list(DEFAULT_SEQUENCES.values())

        # Get custom sequences from database
        stmt = select(Sequence).where(Sequence.is_active == True)
        result = await self.db.execute(stmt)
        db_sequences = result.scalars().all()

        for db_seq in db_sequences:
            steps = [
                SequenceStep(**step) for step in (db_seq.steps or [])
            ]
            sequences.append(SequenceConfig(
                name=db_seq.name,
                description=db_seq.description,
                steps=steps,
                is_active=db_seq.is_active,
            ))

        return sequences

    async def create_sequence(self, config: SequenceConfig) -> Sequence:
        """Create a new custom sequence in the database."""
        # Check if name already exists (including defaults)
        if config.name in DEFAULT_SEQUENCES:
            raise ValueError(f"Sequence name '{config.name}' is reserved")

        existing = await self.db.execute(
            select(Sequence).where(Sequence.name == config.name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Sequence '{config.name}' already exists")

        # Create the sequence
        db_sequence = Sequence(
            name=config.name,
            description=config.description,
            steps=[step.model_dump() for step in config.steps],
            is_active=config.is_active,
        )

        self.db.add(db_sequence)
        await self.db.commit()
        await self.db.refresh(db_sequence)

        logger.info(f"Created custom sequence: {config.name} with {len(config.steps)} steps")
        return db_sequence

    async def update_sequence(
        self,
        sequence_name: str,
        config: SequenceConfig,
    ) -> Sequence | None:
        """Update an existing custom sequence."""
        if sequence_name in DEFAULT_SEQUENCES:
            raise ValueError(f"Cannot modify default sequence: {sequence_name}")

        stmt = select(Sequence).where(Sequence.name == sequence_name)
        result = await self.db.execute(stmt)
        db_sequence = result.scalar_one_or_none()

        if not db_sequence:
            return None

        # Update fields
        db_sequence.description = config.description
        db_sequence.steps = [step.model_dump() for step in config.steps]
        db_sequence.is_active = config.is_active

        await self.db.commit()
        await self.db.refresh(db_sequence)

        logger.info(f"Updated sequence: {sequence_name}")
        return db_sequence

    async def delete_sequence(self, sequence_name: str) -> bool:
        """Delete a custom sequence (soft delete by deactivating)."""
        if sequence_name in DEFAULT_SEQUENCES:
            raise ValueError(f"Cannot delete default sequence: {sequence_name}")

        stmt = select(Sequence).where(Sequence.name == sequence_name)
        result = await self.db.execute(stmt)
        db_sequence = result.scalar_one_or_none()

        if not db_sequence:
            return False

        # Soft delete
        db_sequence.is_active = False
        await self.db.commit()

        logger.info(f"Deleted (deactivated) sequence: {sequence_name}")
        return True

    # =========================================================================
    # Follow-up Logic
    # =========================================================================

    async def should_send_followup(
        self,
        prospect: Prospect,
        step: SequenceStep,
    ) -> FollowUpDecision:
        """
        Determine if a follow-up should be sent to a prospect.

        Checks:
        1. Has prospect replied? → No send
        2. Has prospect bounced/unsubscribed? → No send
        3. Is sequence paused? → No send
        4. Engagement-based logic (opens, clicks)
        """
        # Critical blocks - never send
        if prospect.status == ProspectStatus.REPLIED:
            return FollowUpDecision(should_send=False, reason="prospect_replied")

        if prospect.status == ProspectStatus.OPTED_OUT:
            return FollowUpDecision(should_send=False, reason="prospect_opted_out")

        if prospect.status == ProspectStatus.BOUNCED:
            return FollowUpDecision(should_send=False, reason="email_bounced")

        if prospect.email_status in ["bounced", "complained", "unsubscribed"]:
            return FollowUpDecision(should_send=False, reason=f"email_status_{prospect.email_status}")

        if prospect.sequence_paused:
            return FollowUpDecision(should_send=False, reason=prospect.sequence_paused_reason or "sequence_paused")

        # Get engagement summary for this prospect
        engagement = await self._get_engagement_summary(prospect.id)

        # Engagement-based logic
        if step.skip_if_clicked and engagement["clicks"] > 0:
            return FollowUpDecision(
                should_send=False,
                reason="skip_if_clicked",
            )

        if step.skip_if_opened and engagement["opens"] > 0:
            return FollowUpDecision(
                should_send=False,
                reason="skip_if_opened",
            )

        # Smart adjustments based on engagement patterns
        if engagement["opens"] > 3 and engagement["clicks"] > 0:
            # High engagement but no reply - be more direct
            return FollowUpDecision(
                should_send=True,
                reason="high_engagement_no_reply",
                adjust_tone="more_direct_cta",
            )

        if engagement["opens"] == 0 and step.step_number > 2:
            # No opens at all - try different subject line approach
            return FollowUpDecision(
                should_send=True,
                reason="no_opens_try_new_approach",
                adjust_tone="different_angle",
            )

        # Standard follow-up
        return FollowUpDecision(
            should_send=True,
            reason="standard_followup",
        )

    async def _get_engagement_summary(self, prospect_id: int) -> dict[str, int]:
        """Get engagement summary for a prospect."""
        # Query sent messages for this prospect
        stmt = select(OutreachMessage).where(
            OutreachMessage.prospect_id == prospect_id,
            OutreachMessage.status == MessageStatus.SENT,
        )
        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        summary = {
            "messages_sent": len(messages),
            "opens": sum(m.open_count or 0 for m in messages),
            "clicks": sum(m.click_count or 0 for m in messages),
            "unique_opens": sum(1 for m in messages if m.opened_at),
            "unique_clicks": sum(1 for m in messages if m.clicked_at),
        }

        return summary

    # =========================================================================
    # Scheduling
    # =========================================================================

    async def schedule_next_followup(
        self,
        prospect: Prospect,
        sequence: SequenceConfig | None = None,
    ) -> dict[str, Any]:
        """
        Schedule the next follow-up message for a prospect.

        Returns:
            Dict with scheduling result
        """
        result = {
            "prospect_id": prospect.id,
            "scheduled": False,
            "next_step": None,
            "scheduled_at": None,
            "reason": None,
        }

        # Get sequence
        if not sequence:
            sequence = await self.get_campaign_sequence(prospect.campaign_id)

        # Get current step
        current_step = prospect.current_sequence_step or 0

        # Check if sequence is complete
        if current_step >= len(sequence.steps):
            result["reason"] = "sequence_complete"
            return result

        # Get next step
        next_step_config = sequence.steps[current_step]
        result["next_step"] = current_step + 1

        # Check if should send
        decision = await self.should_send_followup(prospect, next_step_config)

        if not decision.should_send:
            result["reason"] = decision.reason
            return result

        # Calculate send time
        base_time = prospect.sequence_started_at or prospect.created_at or datetime.utcnow()

        # Add delay from step config
        delay = timedelta(
            days=next_step_config.delay_days,
            hours=next_step_config.delay_hours + decision.delay_hours,
        )

        send_at = base_time + delay

        # Ensure send time is in the future
        now = datetime.utcnow()
        if send_at < now:
            send_at = now + timedelta(hours=1)

        # Adjust for business hours (9 AM - 5 PM)
        send_at = self._adjust_for_business_hours(send_at)

        # Update prospect
        prospect.next_followup_at = send_at

        # Create scheduled message (or mark for generation)
        # This would integrate with message generation service

        result["scheduled"] = True
        result["scheduled_at"] = send_at
        result["message_type"] = next_step_config.message_type
        result["adjust_tone"] = decision.adjust_tone

        await self.db.commit()

        logger.info(
            f"Scheduled follow-up for prospect {prospect.id}: "
            f"step={result['next_step']}, send_at={send_at}"
        )

        return result

    async def get_prospects_due_for_followup(
        self,
        campaign_id: int | None = None,
        limit: int = 50,
    ) -> list[Prospect]:
        """
        Get prospects that are due for their next follow-up.

        Returns prospects where:
        - next_followup_at <= now
        - sequence not paused
        - status allows follow-up
        """
        now = datetime.utcnow()

        stmt = select(Prospect).where(
            Prospect.next_followup_at <= now,
            Prospect.sequence_paused == False,
            Prospect.status.in_([
                ProspectStatus.CONTACTED,
                ProspectStatus.ENGAGED,
                ProspectStatus.SCHEDULED,
            ]),
        )

        if campaign_id:
            stmt = stmt.where(Prospect.campaign_id == campaign_id)

        stmt = stmt.order_by(Prospect.next_followup_at).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def advance_prospect_step(self, prospect_id: int) -> bool:
        """Advance a prospect to the next step in the sequence."""
        stmt = (
            update(Prospect)
            .where(Prospect.id == prospect_id)
            .values(current_sequence_step=Prospect.current_sequence_step + 1)
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return True

    async def start_sequence(
        self,
        prospect_id: int,
        sequence_name: str = "standard",
    ) -> dict[str, Any]:
        """
        Start a sequence for a prospect.

        Sets initial values and schedules first message.
        """
        stmt = select(Prospect).where(Prospect.id == prospect_id)
        result = await self.db.execute(stmt)
        prospect = result.scalar_one_or_none()

        if not prospect:
            return {"error": "Prospect not found"}

        # Initialize sequence tracking
        prospect.current_sequence_step = 0
        prospect.sequence_started_at = datetime.utcnow()
        prospect.sequence_paused = False
        prospect.sequence_paused_reason = None

        # Get sequence and schedule first message
        sequence = await self.get_sequence(sequence_name)

        if sequence and sequence.steps:
            first_step = sequence.steps[0]
            # First step delay (usually 0)
            send_at = datetime.utcnow() + timedelta(
                days=first_step.delay_days,
                hours=first_step.delay_hours,
            )
            send_at = self._adjust_for_business_hours(send_at)
            prospect.next_followup_at = send_at

        await self.db.commit()

        return {
            "prospect_id": prospect_id,
            "sequence": sequence_name,
            "started_at": prospect.sequence_started_at,
            "first_send_at": prospect.next_followup_at,
        }

    async def pause_sequence(
        self,
        prospect_id: int,
        reason: str = "Manual pause",
    ) -> bool:
        """Pause a prospect's sequence."""
        stmt = (
            update(Prospect)
            .where(Prospect.id == prospect_id)
            .values(
                sequence_paused=True,
                sequence_paused_reason=reason,
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return True

    async def resume_sequence(self, prospect_id: int) -> bool:
        """Resume a prospect's sequence."""
        stmt = (
            update(Prospect)
            .where(Prospect.id == prospect_id)
            .values(
                sequence_paused=False,
                sequence_paused_reason=None,
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
        return True

    # =========================================================================
    # Helpers
    # =========================================================================

    def _adjust_for_business_hours(
        self,
        dt: datetime,
        start_hour: int = 9,
        end_hour: int = 17,
    ) -> datetime:
        """
        Adjust datetime to fall within business hours.

        Monday-Friday, 9 AM - 5 PM.
        """
        # If weekend, move to Monday
        while dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
            dt += timedelta(days=1)

        # If before start hour, move to start hour
        if dt.hour < start_hour:
            dt = dt.replace(hour=start_hour, minute=0, second=0)

        # If after end hour, move to next day start hour
        if dt.hour >= end_hour:
            dt += timedelta(days=1)
            dt = dt.replace(hour=start_hour, minute=0, second=0)
            # Check for weekend again
            while dt.weekday() >= 5:
                dt += timedelta(days=1)

        return dt

    def get_followup_strategy(self, step_number: int) -> dict[str, str]:
        """Get the messaging strategy for a follow-up step."""
        # Map to 1-4 range for strategies
        strategy_num = min(step_number, 4)
        return FOLLOWUP_STRATEGIES.get(strategy_num, FOLLOWUP_STRATEGIES[1])


# =============================================================================
# Factory Function
# =============================================================================


def get_sequence_service(db_session: AsyncSession) -> SequenceService:
    """Factory function to get SequenceService instance."""
    return SequenceService(db_session)
