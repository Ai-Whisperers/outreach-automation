"""
Integration tests for SQLAlchemy database models.

Tests cover:
- Model creation and persistence
- Relationships between models
- Cascade delete behavior
- Enum handling
- Property methods
- Indexes and constraints
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.outreach_models import (
    DailyQuota,
    EngagementEvent,
    MessageStatus,
    MessageTemplate,
    MessageType,
    OutreachCampaign,
    OutreachChannel,
    OutreachMessage,
    Prospect,
    ProspectStatus,
)


class TestOutreachCampaignModel:
    """Tests for OutreachCampaign model."""

    @pytest.mark.asyncio
    async def test_create_campaign(self, db_session: AsyncSession):
        """Test creating a campaign."""
        campaign = OutreachCampaign(
            name="Test Campaign",
            description="Test description",
            channels=["linkedin", "email"],
            daily_linkedin_limit=20,
            daily_email_limit=50,
            is_active=True,
        )

        db_session.add(campaign)
        await db_session.flush()

        assert campaign.id is not None
        assert campaign.name == "Test Campaign"
        assert campaign.created_at is not None

    @pytest.mark.asyncio
    async def test_campaign_defaults(self, db_session: AsyncSession):
        """Test campaign default values."""
        campaign = OutreachCampaign(name="Minimal Campaign")

        db_session.add(campaign)
        await db_session.flush()

        assert campaign.daily_linkedin_limit == 20
        assert campaign.daily_email_limit == 50
        assert campaign.is_active is False
        assert campaign.channels == []

    @pytest.mark.asyncio
    async def test_campaign_json_fields(self, db_session: AsyncSession):
        """Test JSON field storage."""
        campaign = OutreachCampaign(
            name="JSON Test",
            channels=["linkedin", "email"],
            sequence_config={
                "days_between_followups": [1, 4, 8, 14],
                "max_followups": 4,
            },
        )

        db_session.add(campaign)
        await db_session.flush()
        await db_session.refresh(campaign)

        assert campaign.channels == ["linkedin", "email"]
        assert campaign.sequence_config["max_followups"] == 4

    @pytest.mark.asyncio
    async def test_campaign_repr(self, sample_campaign):
        """Test campaign string representation."""
        repr_str = repr(sample_campaign)

        assert "OutreachCampaign" in repr_str
        assert str(sample_campaign.id) in repr_str
        assert sample_campaign.name in repr_str


class TestProspectModel:
    """Tests for Prospect model."""

    @pytest.mark.asyncio
    async def test_create_prospect(self, db_session: AsyncSession, sample_campaign):
        """Test creating a prospect."""
        prospect = Prospect(
            campaign_id=sample_campaign.id,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            linkedin_url="https://linkedin.com/in/johndoe",
            company="Acme Corp",
            title="VP Marketing",
            industry="Technology",
            status=ProspectStatus.NEW,
        )

        db_session.add(prospect)
        await db_session.flush()

        assert prospect.id is not None
        assert prospect.campaign_id == sample_campaign.id

    @pytest.mark.asyncio
    async def test_prospect_full_name(self, sample_prospect):
        """Test full_name property."""
        assert sample_prospect.full_name == "John Doe"

    @pytest.mark.asyncio
    async def test_prospect_status_enum(self, db_session: AsyncSession, sample_campaign):
        """Test prospect status enum."""
        prospect = Prospect(
            campaign_id=sample_campaign.id,
            first_name="Test",
            last_name="User",
            status=ProspectStatus.RESEARCHED,
        )

        db_session.add(prospect)
        await db_session.flush()
        await db_session.refresh(prospect)

        assert prospect.status == ProspectStatus.RESEARCHED
        assert prospect.status.value == "researched"

    @pytest.mark.asyncio
    async def test_prospect_personalization_data(self, db_session: AsyncSession, sample_campaign):
        """Test JSON personalization data."""
        prospect = Prospect(
            campaign_id=sample_campaign.id,
            first_name="Test",
            last_name="User",
            personalization_data={
                "pain_points": ["Manual moderation", "Scaling"],
                "metrics": {"revenue": "$5M", "employees": 50},
                "icp_type": "sme",
            },
        )

        db_session.add(prospect)
        await db_session.flush()
        await db_session.refresh(prospect)

        assert prospect.personalization_data["icp_type"] == "sme"
        assert len(prospect.personalization_data["pain_points"]) == 2

    @pytest.mark.asyncio
    async def test_prospect_campaign_relationship(self, sample_prospect, sample_campaign):
        """Test prospect-campaign relationship."""
        assert sample_prospect.campaign_id == sample_campaign.id
        assert sample_prospect.campaign.name == sample_campaign.name

    @pytest.mark.asyncio
    async def test_prospect_repr(self, sample_prospect):
        """Test prospect string representation."""
        repr_str = repr(sample_prospect)

        assert "Prospect" in repr_str
        assert sample_prospect.full_name in repr_str


class TestOutreachMessageModel:
    """Tests for OutreachMessage model."""

    @pytest.mark.asyncio
    async def test_create_message(self, db_session: AsyncSession, sample_prospect):
        """Test creating a message."""
        message = OutreachMessage(
            prospect_id=sample_prospect.id,
            channel=OutreachChannel.LINKEDIN,
            message_type=MessageType.CONNECTION_REQUEST,
            content="Hi John, let's connect!",
            status=MessageStatus.DRAFT,
        )

        db_session.add(message)
        await db_session.flush()

        assert message.id is not None
        assert message.channel == OutreachChannel.LINKEDIN

    @pytest.mark.asyncio
    async def test_message_with_subject(self, db_session: AsyncSession, sample_prospect):
        """Test email message with subject."""
        message = OutreachMessage(
            prospect_id=sample_prospect.id,
            channel=OutreachChannel.EMAIL,
            message_type=MessageType.EMAIL_INITIAL,
            subject="Quick question about Acme",
            content="Hi John, I noticed...",
            status=MessageStatus.DRAFT,
        )

        db_session.add(message)
        await db_session.flush()

        assert message.subject == "Quick question about Acme"

    @pytest.mark.asyncio
    async def test_message_character_count(self, sample_message):
        """Test character_count property."""
        assert sample_message.character_count == len(sample_message.content)

    @pytest.mark.asyncio
    async def test_message_word_count(self, sample_message):
        """Test word_count property."""
        assert sample_message.word_count == len(sample_message.content.split())

    @pytest.mark.asyncio
    async def test_message_status_transitions(self, db_session: AsyncSession, sample_message):
        """Test message status transitions."""
        statuses = [
            MessageStatus.APPROVED,
            MessageStatus.SCHEDULED,
            MessageStatus.SENT,
        ]

        for status in statuses:
            sample_message.status = status
            await db_session.flush()
            await db_session.refresh(sample_message)

            assert sample_message.status == status

    @pytest.mark.asyncio
    async def test_message_scheduling(self, db_session: AsyncSession, sample_prospect):
        """Test message scheduling fields."""
        scheduled_time = datetime.utcnow() + timedelta(hours=2)

        message = OutreachMessage(
            prospect_id=sample_prospect.id,
            channel=OutreachChannel.EMAIL,
            message_type=MessageType.EMAIL_INITIAL,
            content="Scheduled message",
            status=MessageStatus.SCHEDULED,
            scheduled_at=scheduled_time,
        )

        db_session.add(message)
        await db_session.flush()

        assert message.scheduled_at == scheduled_time
        assert message.sent_at is None

    @pytest.mark.asyncio
    async def test_message_personalization_metadata(self, db_session: AsyncSession, sample_prospect):
        """Test message personalization metadata."""
        message = OutreachMessage(
            prospect_id=sample_prospect.id,
            channel=OutreachChannel.EMAIL,
            message_type=MessageType.EMAIL_INITIAL,
            content="Personalized message",
            personalization_used={
                "pain_points_used": ["Manual moderation"],
                "metrics_used": ["$5M revenue"],
                "personalization_score": 0.85,
            },
        )

        db_session.add(message)
        await db_session.flush()
        await db_session.refresh(message)

        assert message.personalization_used["personalization_score"] == 0.85

    @pytest.mark.asyncio
    async def test_message_prospect_relationship(self, sample_message, sample_prospect):
        """Test message-prospect relationship."""
        assert sample_message.prospect_id == sample_prospect.id
        assert sample_message.prospect.first_name == sample_prospect.first_name


class TestEngagementEventModel:
    """Tests for EngagementEvent model."""

    @pytest.mark.asyncio
    async def test_create_event(self, db_session: AsyncSession, sample_prospect, sample_message):
        """Test creating an engagement event."""
        event = EngagementEvent(
            prospect_id=sample_prospect.id,
            message_id=sample_message.id,
            event_type="open",
            channel=OutreachChannel.EMAIL,
            metadata={"ip": "192.168.1.1", "user_agent": "Mozilla/5.0"},
        )

        db_session.add(event)
        await db_session.flush()

        assert event.id is not None
        assert event.event_type == "open"
        assert event.occurred_at is not None

    @pytest.mark.asyncio
    async def test_event_types(self, db_session: AsyncSession, sample_prospect):
        """Test various event types."""
        event_types = [
            "open", "click", "reply", "connection_accepted",
            "bounce", "unsubscribe",
        ]

        for event_type in event_types:
            event = EngagementEvent(
                prospect_id=sample_prospect.id,
                event_type=event_type,
                channel=OutreachChannel.EMAIL,
            )
            db_session.add(event)

        await db_session.flush()

        result = await db_session.execute(
            select(EngagementEvent).where(
                EngagementEvent.prospect_id == sample_prospect.id
            )
        )
        events = result.scalars().all()

        assert len(events) == len(event_types)

    @pytest.mark.asyncio
    async def test_event_without_message(self, db_session: AsyncSession, sample_prospect):
        """Test event without associated message."""
        event = EngagementEvent(
            prospect_id=sample_prospect.id,
            message_id=None,  # No message
            event_type="connection_accepted",
            channel=OutreachChannel.LINKEDIN,
        )

        db_session.add(event)
        await db_session.flush()

        assert event.message_id is None


class TestMessageTemplateModel:
    """Tests for MessageTemplate model."""

    @pytest.mark.asyncio
    async def test_create_template(self, db_session: AsyncSession, sample_campaign):
        """Test creating a message template."""
        template = MessageTemplate(
            campaign_id=sample_campaign.id,
            name="Cold Email Template A",
            channel=OutreachChannel.EMAIL,
            message_type=MessageType.EMAIL_INITIAL,
            language="en",
            subject_template="Hi {{first_name}} - quick question",
            content_template="Hi {{first_name}}, I noticed {{company}}...",
            variant="A",
        )

        db_session.add(template)
        await db_session.flush()

        assert template.id is not None
        assert template.is_active is True

    @pytest.mark.asyncio
    async def test_template_variants(self, db_session: AsyncSession, sample_campaign):
        """Test A/B test variants."""
        for variant in ["A", "B", "C"]:
            template = MessageTemplate(
                campaign_id=sample_campaign.id,
                name=f"Template {variant}",
                channel=OutreachChannel.EMAIL,
                message_type=MessageType.EMAIL_INITIAL,
                content_template=f"Content for variant {variant}",
                variant=variant,
            )
            db_session.add(template)

        await db_session.flush()

        result = await db_session.execute(
            select(MessageTemplate).where(
                MessageTemplate.campaign_id == sample_campaign.id
            )
        )
        templates = result.scalars().all()

        assert len(templates) == 3
        variants = {t.variant for t in templates}
        assert variants == {"A", "B", "C"}

    @pytest.mark.asyncio
    async def test_template_languages(self, db_session: AsyncSession, sample_campaign):
        """Test multilingual templates."""
        for lang in ["en", "es", "pt"]:
            template = MessageTemplate(
                campaign_id=sample_campaign.id,
                name=f"Template {lang}",
                channel=OutreachChannel.EMAIL,
                message_type=MessageType.EMAIL_INITIAL,
                language=lang,
                content_template=f"Content in {lang}",
            )
            db_session.add(template)

        await db_session.flush()


class TestDailyQuotaModel:
    """Tests for DailyQuota model."""

    @pytest.mark.asyncio
    async def test_create_quota(self, db_session: AsyncSession, sample_campaign):
        """Test creating daily quota."""
        quota = DailyQuota(
            date=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            channel=OutreachChannel.LINKEDIN,
            campaign_id=sample_campaign.id,
            sent_count=5,
            limit=20,
        )

        db_session.add(quota)
        await db_session.flush()

        assert quota.id is not None
        assert quota.sent_count == 5

    @pytest.mark.asyncio
    async def test_quota_repr(self, db_session: AsyncSession, sample_campaign):
        """Test quota string representation."""
        quota = DailyQuota(
            date=datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            channel=OutreachChannel.EMAIL,
            campaign_id=sample_campaign.id,
            sent_count=10,
            limit=50,
        )

        db_session.add(quota)
        await db_session.flush()

        repr_str = repr(quota)

        assert "DailyQuota" in repr_str
        assert "10/50" in repr_str


class TestRelationships:
    """Tests for model relationships."""

    @pytest.mark.asyncio
    async def test_campaign_prospects_relationship(
        self, db_session: AsyncSession, sample_campaign
    ):
        """Test campaign has many prospects."""
        for i in range(3):
            prospect = Prospect(
                campaign_id=sample_campaign.id,
                first_name=f"User{i}",
                last_name="Test",
            )
            db_session.add(prospect)

        await db_session.flush()
        await db_session.refresh(sample_campaign)

        assert len(sample_campaign.prospects) == 3

    @pytest.mark.asyncio
    async def test_prospect_messages_relationship(
        self, db_session: AsyncSession, sample_prospect
    ):
        """Test prospect has many messages."""
        for msg_type in [MessageType.CONNECTION_REQUEST, MessageType.EMAIL_INITIAL]:
            message = OutreachMessage(
                prospect_id=sample_prospect.id,
                channel=OutreachChannel.LINKEDIN,
                message_type=msg_type,
                content="Test message",
            )
            db_session.add(message)

        await db_session.flush()
        await db_session.refresh(sample_prospect)

        assert len(sample_prospect.messages) == 2

    @pytest.mark.asyncio
    async def test_prospect_events_relationship(
        self, db_session: AsyncSession, sample_prospect
    ):
        """Test prospect has many events."""
        for event_type in ["open", "click"]:
            event = EngagementEvent(
                prospect_id=sample_prospect.id,
                event_type=event_type,
                channel=OutreachChannel.EMAIL,
            )
            db_session.add(event)

        await db_session.flush()
        await db_session.refresh(sample_prospect)

        assert len(sample_prospect.events) == 2


class TestCascadeDelete:
    """Tests for cascade delete behavior."""

    @pytest.mark.asyncio
    async def test_delete_campaign_cascades_prospects(
        self, db_session: AsyncSession, sample_campaign, sample_prospect
    ):
        """Test deleting campaign cascades to prospects."""
        prospect_id = sample_prospect.id

        await db_session.delete(sample_campaign)
        await db_session.flush()

        # Verify prospect was deleted
        result = await db_session.execute(
            select(Prospect).where(Prospect.id == prospect_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_prospect_cascades_messages(
        self, db_session: AsyncSession, sample_prospect, sample_message
    ):
        """Test deleting prospect cascades to messages."""
        message_id = sample_message.id

        await db_session.delete(sample_prospect)
        await db_session.flush()

        # Verify message was deleted
        result = await db_session.execute(
            select(OutreachMessage).where(OutreachMessage.id == message_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_prospect_cascades_events(
        self, db_session: AsyncSession, sample_prospect
    ):
        """Test deleting prospect cascades to events."""
        event = EngagementEvent(
            prospect_id=sample_prospect.id,
            event_type="open",
            channel=OutreachChannel.EMAIL,
        )
        db_session.add(event)
        await db_session.flush()

        event_id = event.id

        await db_session.delete(sample_prospect)
        await db_session.flush()

        # Verify event was deleted
        result = await db_session.execute(
            select(EngagementEvent).where(EngagementEvent.id == event_id)
        )
        assert result.scalar_one_or_none() is None


class TestEnums:
    """Tests for enum values and behavior."""

    def test_prospect_status_values(self):
        """Test all prospect status enum values."""
        expected = [
            "new", "researched", "scheduled", "contacted",
            "connected", "engaged", "replied", "meeting_scheduled",
            "converted", "opted_out", "bounced",
        ]

        values = [s.value for s in ProspectStatus]
        assert set(values) == set(expected)

    def test_outreach_channel_values(self):
        """Test outreach channel enum values."""
        assert OutreachChannel.LINKEDIN.value == "linkedin"
        assert OutreachChannel.EMAIL.value == "email"

    def test_message_type_values(self):
        """Test message type enum values."""
        expected = [
            "connection_request", "linkedin_message",
            "email_initial", "email_followup_1",
            "email_followup_2", "email_followup_3",
            "email_followup_4",
        ]

        values = [t.value for t in MessageType]
        assert set(values) == set(expected)

    def test_message_status_values(self):
        """Test message status enum values."""
        expected = [
            "draft", "approved", "scheduled",
            "sent", "failed", "cancelled",
        ]

        values = [s.value for s in MessageStatus]
        assert set(values) == set(expected)
