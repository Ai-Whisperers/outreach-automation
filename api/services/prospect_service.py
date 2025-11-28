"""
Prospect management service with CSV import functionality.

Handles:
- CSV parsing and validation
- Prospect CRUD operations
- Deduplication by email/LinkedIn URL
- Auto-linking to brand briefs
"""

import csv
import io
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.outreach_models import (
    EngagementEvent,
    OutreachCampaign,
    OutreachMessage,
    Prospect,
    ProspectStatus,
)
from ..logging_config import get_logger

logger = get_logger("services.prospect")


class ProspectService:
    """
    Service for managing prospects and CSV imports.
    """

    def __init__(self, session: AsyncSession, brand_briefs_dir: Path | None = None):
        self.session = session
        self.brand_briefs_dir = brand_briefs_dir or Path("../11-Brand-Briefs")

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create_prospect(
        self,
        campaign_id: int,
        first_name: str,
        last_name: str,
        email: str | None = None,
        linkedin_url: str | None = None,
        company: str | None = None,
        title: str | None = None,
        industry: str | None = None,
        location: str | None = None,
        pain_points: list[str] | None = None,
        metrics: dict | None = None,
        auto_link_brand_brief: bool = True,
    ) -> Prospect:
        """Create a single prospect."""
        # Build personalization data
        personalization_data = {}
        if pain_points:
            personalization_data["pain_points"] = pain_points
        if metrics:
            personalization_data["metrics"] = metrics

        prospect = Prospect(
            campaign_id=campaign_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            linkedin_url=linkedin_url,
            company=company,
            title=title,
            industry=industry,
            location=location,
            personalization_data=personalization_data if personalization_data else None,
            status=ProspectStatus.NEW,
        )

        # Auto-link to brand brief
        if auto_link_brand_brief and company:
            brief_path = self._find_brand_brief(company)
            if brief_path:
                prospect.brand_brief_path = str(brief_path)
                logger.info(f"Auto-linked prospect to brand brief: {brief_path}")

        self.session.add(prospect)
        await self.session.flush()
        await self.session.refresh(prospect)

        logger.info(
            f"Created prospect: {prospect.full_name} at {company} (ID: {prospect.id})"
        )
        return prospect

    async def get_prospect(self, prospect_id: int) -> Prospect | None:
        """Get a prospect by ID."""
        result = await self.session.execute(
            select(Prospect).where(Prospect.id == prospect_id)
        )
        return result.scalar_one_or_none()

    async def get_prospects(
        self,
        campaign_id: int,
        status: ProspectStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Prospect], int]:
        """Get prospects with optional filtering."""
        query = select(Prospect).where(Prospect.campaign_id == campaign_id)

        if status:
            query = query.where(Prospect.status == status)

        # Get total count
        count_query = (
            select(func.count())
            .select_from(Prospect)
            .where(Prospect.campaign_id == campaign_id)
        )
        if status:
            count_query = count_query.where(Prospect.status == status)
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Get prospects with pagination
        query = query.order_by(Prospect.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(query)
        prospects = list(result.scalars().all())

        return prospects, total

    async def update_prospect(
        self, prospect_id: int, **updates
    ) -> Prospect | None:
        """Update a prospect."""
        prospect = await self.get_prospect(prospect_id)
        if not prospect:
            return None

        for key, value in updates.items():
            if hasattr(prospect, key) and value is not None:
                setattr(prospect, key, value)

        prospect.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(prospect)

        logger.info(f"Updated prospect {prospect_id}")
        return prospect

    async def delete_prospect(self, prospect_id: int) -> bool:
        """Delete a prospect."""
        prospect = await self.get_prospect(prospect_id)
        if not prospect:
            return False

        await self.session.delete(prospect)
        await self.session.flush()
        logger.info(f"Deleted prospect {prospect_id}")
        return True

    async def update_status(
        self, prospect_id: int, status: ProspectStatus
    ) -> Prospect | None:
        """Update prospect status."""
        prospect = await self.get_prospect(prospect_id)
        if not prospect:
            return None

        prospect.status = status
        prospect.updated_at = datetime.utcnow()

        if status == ProspectStatus.CONTACTED:
            prospect.last_contacted_at = datetime.utcnow()

        await self.session.flush()
        logger.info(f"Updated prospect {prospect_id} status to {status.value}")
        return prospect

    # =========================================================================
    # CSV Import
    # =========================================================================

    async def import_from_csv(
        self,
        campaign_id: int,
        csv_content: str,
        skip_duplicates: bool = True,
        auto_link_brand_briefs: bool = True,
    ) -> dict[str, Any]:
        """
        Import prospects from CSV content.

        Expected CSV columns:
        - first_name (required)
        - last_name (required)
        - email (optional)
        - linkedin_url (optional)
        - company (optional)
        - title (optional)
        - industry (optional)
        - location (optional)
        - pain_points (optional, comma-separated)
        - metrics (optional, JSON string)

        Returns:
            {
                "added_count": int,
                "duplicates_skipped": int,
                "invalid_skipped": int,
                "errors": list[str]
            }
        """
        logger.info(f"Starting CSV import for campaign {campaign_id}")

        result = {
            "added_count": 0,
            "duplicates_skipped": 0,
            "invalid_skipped": 0,
            "errors": [],
        }

        # Parse CSV
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(reader)
        except Exception as e:
            logger.error(f"Failed to parse CSV: {e}")
            result["errors"].append(f"Failed to parse CSV: {str(e)}")
            return result

        if not rows:
            result["errors"].append("CSV is empty")
            return result

        # Validate required columns
        required_cols = {"first_name", "last_name"}
        if rows:
            available_cols = set(rows[0].keys())
            missing_cols = required_cols - available_cols
            if missing_cols:
                result["errors"].append(
                    f"Missing required columns: {', '.join(missing_cols)}"
                )
                return result

        # Get existing emails and LinkedIn URLs for deduplication
        existing_emails = set()
        existing_linkedin = set()

        if skip_duplicates:
            existing_result = await self.session.execute(
                select(Prospect.email, Prospect.linkedin_url).where(
                    Prospect.campaign_id == campaign_id
                )
            )
            for row in existing_result:
                if row.email:
                    existing_emails.add(row.email.lower())
                if row.linkedin_url:
                    existing_linkedin.add(row.linkedin_url.lower())

        # Process each row
        for i, row in enumerate(rows, start=2):  # Start at 2 (header is row 1)
            try:
                # Validate required fields
                first_name = row.get("first_name", "").strip()
                last_name = row.get("last_name", "").strip()

                if not first_name or not last_name:
                    result["invalid_skipped"] += 1
                    result["errors"].append(
                        f"Row {i}: Missing first_name or last_name"
                    )
                    continue

                # Get optional fields
                email = row.get("email", "").strip() or None
                linkedin_url = row.get("linkedin_url", "").strip() or None
                company = row.get("company", "").strip() or None
                title = row.get("title", "").strip() or None
                industry = row.get("industry", "").strip() or None
                location = row.get("location", "").strip() or None

                # Validate email format
                if email and not self._is_valid_email(email):
                    result["invalid_skipped"] += 1
                    result["errors"].append(f"Row {i}: Invalid email format: {email}")
                    continue

                # Validate LinkedIn URL
                if linkedin_url and "linkedin.com" not in linkedin_url.lower():
                    result["invalid_skipped"] += 1
                    result["errors"].append(
                        f"Row {i}: Invalid LinkedIn URL: {linkedin_url}"
                    )
                    continue

                # Check for duplicates
                if skip_duplicates:
                    if email and email.lower() in existing_emails:
                        result["duplicates_skipped"] += 1
                        continue
                    if linkedin_url and linkedin_url.lower() in existing_linkedin:
                        result["duplicates_skipped"] += 1
                        continue

                # Parse pain_points (comma-separated)
                pain_points = None
                pain_points_str = row.get("pain_points", "").strip()
                if pain_points_str:
                    pain_points = [
                        p.strip() for p in pain_points_str.split(",") if p.strip()
                    ]

                # Parse metrics (JSON)
                metrics = None
                metrics_str = row.get("metrics", "").strip()
                if metrics_str:
                    try:
                        metrics = json.loads(metrics_str)
                    except json.JSONDecodeError:
                        logger.warning(f"Row {i}: Invalid metrics JSON, skipping field")

                # Create prospect
                await self.create_prospect(
                    campaign_id=campaign_id,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    linkedin_url=linkedin_url,
                    company=company,
                    title=title,
                    industry=industry,
                    location=location,
                    pain_points=pain_points,
                    metrics=metrics,
                    auto_link_brand_brief=auto_link_brand_briefs,
                )

                result["added_count"] += 1

                # Track for deduplication within batch
                if email:
                    existing_emails.add(email.lower())
                if linkedin_url:
                    existing_linkedin.add(linkedin_url.lower())

            except Exception as e:
                result["invalid_skipped"] += 1
                result["errors"].append(f"Row {i}: Error processing - {str(e)}")
                logger.error(f"Error processing row {i}: {e}")

        logger.info(
            f"CSV import complete: {result['added_count']} added, "
            f"{result['duplicates_skipped']} duplicates, "
            f"{result['invalid_skipped']} invalid"
        )

        return result

    # =========================================================================
    # Brand Brief Linking
    # =========================================================================

    def _find_brand_brief(self, company_name: str) -> Path | None:
        """
        Find a brand brief matching the company name.

        Searches in 11-Brand-Briefs/ directory structure.
        """
        if not self.brand_briefs_dir.exists():
            logger.warning(f"Brand briefs directory not found: {self.brand_briefs_dir}")
            return None

        # Normalize company name for matching
        normalized = self._normalize_company_name(company_name)

        # Search through all subdirectories
        for brief_path in self.brand_briefs_dir.rglob("*.md"):
            brief_name = self._normalize_company_name(brief_path.stem)

            # Check for match
            if normalized in brief_name or brief_name in normalized:
                return brief_path

        return None

    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for matching."""
        # Remove common suffixes
        name = re.sub(
            r"\s+(inc|llc|ltd|corp|co|company|corporation)\.?$",
            "",
            name,
            flags=re.IGNORECASE,
        )
        # Convert to lowercase, remove non-alphanumeric
        return re.sub(r"[^a-z0-9]", "", name.lower())

    async def link_brand_brief(
        self, prospect_id: int, brand_brief_path: str
    ) -> Prospect | None:
        """Manually link a prospect to a brand brief."""
        prospect = await self.get_prospect(prospect_id)
        if not prospect:
            return None

        prospect.brand_brief_path = brand_brief_path
        prospect.updated_at = datetime.utcnow()
        await self.session.flush()

        logger.info(f"Linked prospect {prospect_id} to brand brief: {brand_brief_path}")
        return prospect

    # =========================================================================
    # Prospect Queries
    # =========================================================================

    async def get_prospects_for_outreach(
        self,
        campaign_id: int,
        channel: str,
        limit: int,
    ) -> list[Prospect]:
        """Get prospects ready for initial outreach."""
        query = select(Prospect).where(
            Prospect.campaign_id == campaign_id,
            Prospect.status.in_([ProspectStatus.NEW, ProspectStatus.RESEARCHED]),
        )

        # Filter by channel requirements
        if channel == "linkedin":
            query = query.where(Prospect.linkedin_url.isnot(None))
        elif channel == "email":
            query = query.where(Prospect.email.isnot(None))

        # Order by engagement score (higher priority first)
        query = query.order_by(Prospect.engagement_score.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_pending_connections(self, campaign_id: int) -> list[Prospect]:
        """Get prospects with pending LinkedIn connection requests."""
        result = await self.session.execute(
            select(Prospect).where(
                Prospect.campaign_id == campaign_id,
                Prospect.status == ProspectStatus.CONTACTED,
                Prospect.linkedin_url.isnot(None),
            )
        )
        return list(result.scalars().all())

    async def get_prospect_timeline(
        self, prospect_id: int
    ) -> list[dict[str, Any]]:
        """Get full interaction timeline for a prospect."""
        prospect = await self.get_prospect(prospect_id)
        if not prospect:
            return []

        timeline = []

        # Add creation event
        timeline.append(
            {
                "timestamp": prospect.created_at.isoformat(),
                "event_type": "created",
                "channel": None,
                "details": {"status": "new"},
            }
        )

        # Get all messages
        messages_result = await self.session.execute(
            select(OutreachMessage)
            .where(OutreachMessage.prospect_id == prospect_id)
            .order_by(OutreachMessage.created_at)
        )
        for msg in messages_result.scalars():
            if msg.sent_at:
                timeline.append(
                    {
                        "timestamp": msg.sent_at.isoformat(),
                        "event_type": f"message_sent_{msg.message_type.value}",
                        "channel": msg.channel.value,
                        "details": {
                            "message_id": msg.id,
                            "subject": msg.subject,
                        },
                    }
                )

        # Get all engagement events
        events_result = await self.session.execute(
            select(EngagementEvent)
            .where(EngagementEvent.prospect_id == prospect_id)
            .order_by(EngagementEvent.occurred_at)
        )
        for event in events_result.scalars():
            timeline.append(
                {
                    "timestamp": event.occurred_at.isoformat(),
                    "event_type": event.event_type,
                    "channel": event.channel.value,
                    "details": event.metadata,
                }
            )

        # Sort by timestamp
        timeline.sort(key=lambda x: x["timestamp"])

        return timeline

    async def get_message_count(self, prospect_id: int) -> int:
        """Get count of messages for a prospect."""
        result = await self.session.execute(
            select(func.count())
            .select_from(OutreachMessage)
            .where(OutreachMessage.prospect_id == prospect_id)
        )
        return result.scalar() or 0

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def _is_valid_email(self, email: str) -> bool:
        """Validate email format."""
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, email))

    async def check_duplicate(
        self, campaign_id: int, email: str | None, linkedin_url: str | None
    ) -> bool:
        """Check if a prospect already exists."""
        conditions = [Prospect.campaign_id == campaign_id]

        if email:
            conditions.append(Prospect.email == email)
        if linkedin_url:
            conditions.append(Prospect.linkedin_url == linkedin_url)

        if len(conditions) == 1:
            return False  # No email or LinkedIn to check

        result = await self.session.execute(
            select(Prospect).where(and_(*conditions)).limit(1)
        )
        return result.scalar_one_or_none() is not None

    # =========================================================================
    # Message Operations (for outreach routes)
    # =========================================================================

    async def get_message(self, message_id: int) -> dict | None:
        """Get a message by ID."""
        result = await self.session.execute(
            select(OutreachMessage).where(OutreachMessage.id == message_id)
        )
        message = result.scalar_one_or_none()
        if not message:
            return None

        # Get prospect for campaign_id
        prospect = await self.get_prospect(message.prospect_id)

        return {
            "id": message.id,
            "prospect_id": message.prospect_id,
            "campaign_id": prospect.campaign_id if prospect else None,
            "channel": message.channel.value,
            "message_type": message.message_type.value,
            "subject": message.subject,
            "content": message.content,
            "status": message.status.value,
            "scheduled_at": message.scheduled_at.isoformat() if message.scheduled_at else None,
            "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        }

    async def update_message(self, message_id: int, updates: dict) -> bool:
        """Update a message."""
        result = await self.session.execute(
            select(OutreachMessage).where(OutreachMessage.id == message_id)
        )
        message = result.scalar_one_or_none()
        if not message:
            return False

        for key, value in updates.items():
            if hasattr(message, key) and value is not None:
                setattr(message, key, value)

        await self.session.flush()
        logger.info(f"Updated message {message_id}")
        return True

    async def schedule_message(
        self,
        message_id: int,
        scheduled_time: str | None,
        channel: str,
    ) -> bool:
        """Schedule a message for sending."""
        from ..database.outreach_models import MessageStatus

        result = await self.session.execute(
            select(OutreachMessage).where(OutreachMessage.id == message_id)
        )
        message = result.scalar_one_or_none()
        if not message:
            return False

        message.status = MessageStatus.SCHEDULED
        if scheduled_time:
            message.scheduled_at = datetime.fromisoformat(scheduled_time.replace("Z", "+00:00"))
        else:
            message.scheduled_at = datetime.utcnow()

        await self.session.flush()
        logger.info(f"Scheduled message {message_id} for {message.scheduled_at}")
        return True

    async def get_messages_for_scheduling(
        self,
        campaign_id: int,
        channel: str,
        limit: int,
    ) -> list[dict]:
        """Get messages ready to be scheduled."""
        from ..database.outreach_models import MessageStatus, OutreachChannel

        channel_enum = OutreachChannel.LINKEDIN if channel == "linkedin" else OutreachChannel.EMAIL

        query = (
            select(OutreachMessage)
            .join(Prospect)
            .where(
                Prospect.campaign_id == campaign_id,
                OutreachMessage.channel == channel_enum,
                OutreachMessage.status == MessageStatus.APPROVED,
            )
            .limit(limit)
        )

        result = await self.session.execute(query)
        messages = result.scalars().all()

        return [
            {
                "id": m.id,
                "prospect_id": m.prospect_id,
                "channel": m.channel.value,
                "content": m.content,
                "subject": m.subject,
            }
            for m in messages
        ]

    async def schedule_batch(
        self,
        messages: list[dict],
        start_time: datetime,
        channel: str,
    ) -> int:
        """Schedule a batch of messages with staggered timing."""
        from ..database.outreach_models import MessageStatus
        import random

        scheduled_count = 0
        current_time = start_time

        for msg in messages:
            result = await self.session.execute(
                select(OutreachMessage).where(OutreachMessage.id == msg["id"])
            )
            message = result.scalar_one_or_none()
            if message:
                message.status = MessageStatus.SCHEDULED
                message.scheduled_at = current_time
                scheduled_count += 1

                # Add random delay between 2-5 minutes
                delay_seconds = random.randint(120, 300)
                current_time = current_time + timedelta(seconds=delay_seconds)

        await self.session.flush()
        logger.info(f"Scheduled {scheduled_count} messages starting at {start_time}")
        return scheduled_count

    async def get_due_messages(
        self,
        campaign_id: int,
        channel: str,
    ) -> list[dict]:
        """Get messages that are due for sending."""
        from ..database.outreach_models import MessageStatus, OutreachChannel

        channel_enum = OutreachChannel.LINKEDIN if channel == "linkedin" else OutreachChannel.EMAIL
        now = datetime.utcnow()

        query = (
            select(OutreachMessage)
            .join(Prospect)
            .where(
                Prospect.campaign_id == campaign_id,
                OutreachMessage.channel == channel_enum,
                OutreachMessage.status == MessageStatus.SCHEDULED,
                OutreachMessage.scheduled_at <= now,
            )
            .order_by(OutreachMessage.scheduled_at)
        )

        result = await self.session.execute(query)
        messages = result.scalars().all()

        return [
            {
                "id": m.id,
                "prospect_id": m.prospect_id,
                "channel": m.channel.value,
                "content": m.content,
                "subject": m.subject,
            }
            for m in messages
        ]

    # =========================================================================
    # Analytics Operations
    # =========================================================================

    async def get_analytics_dashboard(
        self,
        campaign_id: int | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Get analytics dashboard data."""
        from ..database.outreach_models import MessageStatus

        # Base queries
        prospect_query = select(func.count()).select_from(Prospect)
        message_query = select(func.count()).select_from(OutreachMessage)

        if campaign_id:
            prospect_query = prospect_query.where(Prospect.campaign_id == campaign_id)
            message_query = message_query.join(Prospect).where(Prospect.campaign_id == campaign_id)

        # Get counts
        total_prospects = (await self.session.execute(prospect_query)).scalar() or 0

        sent_query = message_query.where(OutreachMessage.status == MessageStatus.SENT)
        total_sent = (await self.session.execute(sent_query)).scalar() or 0

        # Get engagement counts
        opened_query = select(func.count()).select_from(OutreachMessage).where(
            OutreachMessage.opened_at.isnot(None)
        )
        clicked_query = select(func.count()).select_from(OutreachMessage).where(
            OutreachMessage.clicked_at.isnot(None)
        )

        if campaign_id:
            opened_query = opened_query.join(Prospect).where(Prospect.campaign_id == campaign_id)
            clicked_query = clicked_query.join(Prospect).where(Prospect.campaign_id == campaign_id)

        total_opened = (await self.session.execute(opened_query)).scalar() or 0
        total_clicked = (await self.session.execute(clicked_query)).scalar() or 0

        # Get reply count
        replied_query = select(func.count()).select_from(Prospect).where(
            Prospect.status == ProspectStatus.REPLIED
        )
        if campaign_id:
            replied_query = replied_query.where(Prospect.campaign_id == campaign_id)
        total_replied = (await self.session.execute(replied_query)).scalar() or 0

        # Calculate rates
        open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
        click_rate = (total_clicked / total_sent * 100) if total_sent > 0 else 0
        reply_rate = (total_replied / total_sent * 100) if total_sent > 0 else 0

        return {
            "total_prospects": total_prospects,
            "total_sent": total_sent,
            "total_opened": total_opened,
            "total_clicked": total_clicked,
            "total_replied": total_replied,
            "open_rate": round(open_rate, 2),
            "click_rate": round(click_rate, 2),
            "reply_rate": round(reply_rate, 2),
            "campaign_id": campaign_id,
        }

    async def get_engagement_by_channel(
        self,
        campaign_id: int | None = None,
        days: int = 30,
    ) -> dict:
        """Get engagement stats by channel."""
        from ..database.outreach_models import OutreachChannel, MessageStatus

        results = {}
        for channel in [OutreachChannel.EMAIL, OutreachChannel.LINKEDIN]:
            query = select(func.count()).select_from(OutreachMessage).where(
                OutreachMessage.channel == channel,
                OutreachMessage.status == MessageStatus.SENT,
            )

            if campaign_id:
                query = query.join(Prospect).where(Prospect.campaign_id == campaign_id)

            sent = (await self.session.execute(query)).scalar() or 0

            # Opened
            opened_query = select(func.count()).select_from(OutreachMessage).where(
                OutreachMessage.channel == channel,
                OutreachMessage.opened_at.isnot(None),
            )
            if campaign_id:
                opened_query = opened_query.join(Prospect).where(Prospect.campaign_id == campaign_id)
            opened = (await self.session.execute(opened_query)).scalar() or 0

            results[channel.value] = {
                "sent": sent,
                "opened": opened,
                "open_rate": round((opened / sent * 100) if sent > 0 else 0, 2),
            }

        return results

    async def get_daily_stats(
        self,
        campaign_id: int | None = None,
        days: int = 14,
    ) -> list[dict]:
        """Get daily outreach statistics."""
        from ..database.outreach_models import MessageStatus

        stats = []
        today = datetime.utcnow().date()

        for i in range(days):
            day = today - timedelta(days=i)
            day_start = datetime.combine(day, datetime.min.time())
            day_end = datetime.combine(day, datetime.max.time())

            # Sent count
            sent_query = select(func.count()).select_from(OutreachMessage).where(
                OutreachMessage.sent_at >= day_start,
                OutreachMessage.sent_at <= day_end,
            )
            if campaign_id:
                sent_query = sent_query.join(Prospect).where(Prospect.campaign_id == campaign_id)
            sent = (await self.session.execute(sent_query)).scalar() or 0

            # Opened count
            opened_query = select(func.count()).select_from(OutreachMessage).where(
                OutreachMessage.opened_at >= day_start,
                OutreachMessage.opened_at <= day_end,
            )
            if campaign_id:
                opened_query = opened_query.join(Prospect).where(Prospect.campaign_id == campaign_id)
            opened = (await self.session.execute(opened_query)).scalar() or 0

            stats.append({
                "date": day.isoformat(),
                "sent": sent,
                "opened": opened,
                "open_rate": round((opened / sent * 100) if sent > 0 else 0, 2),
            })

        return stats

    async def get_campaign_analytics(self, campaign_id: int) -> dict | None:
        """Get analytics for a specific campaign."""
        # Check campaign exists
        result = await self.session.execute(
            select(OutreachCampaign).where(OutreachCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return None

        # Get prospect count
        prospect_count = (await self.session.execute(
            select(func.count()).select_from(Prospect).where(Prospect.campaign_id == campaign_id)
        )).scalar() or 0

        # Get message stats
        analytics = await self.get_analytics_dashboard(campaign_id=campaign_id)

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign.name,
            "total_prospects": prospect_count,
            "messages_sent": analytics["total_sent"],
            "messages_opened": analytics["total_opened"],
            "messages_clicked": analytics["total_clicked"],
            "messages_replied": analytics["total_replied"],
            "connections_sent": 0,  # TODO: track LinkedIn connections separately
            "connections_accepted": 0,
            "open_rate": analytics["open_rate"],
            "click_rate": analytics["click_rate"],
            "reply_rate": analytics["reply_rate"],
            "connection_rate": 0.0,
        }

    async def activate_campaign(self, campaign_id: int) -> dict | None:
        """Activate a campaign for outreach."""
        result = await self.session.execute(
            select(OutreachCampaign).where(OutreachCampaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return None

        campaign.is_active = True
        campaign.started_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(campaign)

        logger.info(f"Activated campaign {campaign_id}")

        return {
            "id": campaign.id,
            "name": campaign.name,
            "is_active": campaign.is_active,
            "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
        }


def get_prospect_service(
    session: AsyncSession | None = None, brand_briefs_dir: Path | None = None
) -> ProspectService:
    """Factory function to get ProspectService instance."""
    # If no session provided, create a simple mock for compatibility
    # In production, session should always be provided via dependency injection
    if session is None:
        from ..database.engine import async_session_maker
        # This is a fallback - routes should provide session via DI
        import asyncio
        loop = asyncio.get_event_loop()
        session = loop.run_until_complete(async_session_maker().__aenter__())
    return ProspectService(session, brand_briefs_dir)
