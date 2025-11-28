"""
SQLAlchemy models for outreach automation.

State machine for prospects:
new → researched → scheduled → contacted → connected → engaged → replied → converted
                                    ↓           ↓
                              (bounced)   (opted_out)
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Base


# =============================================================================
# Enums
# =============================================================================


class ProspectStatus(str, Enum):
    """State machine for prospect journey."""

    NEW = "new"  # Just added
    RESEARCHED = "researched"  # Research/personalization completed
    SCHEDULED = "scheduled"  # Outreach scheduled
    CONTACTED = "contacted"  # Initial outreach sent
    CONNECTED = "connected"  # LinkedIn connection accepted
    ENGAGED = "engaged"  # Opened email / viewed profile
    REPLIED = "replied"  # Responded to outreach
    MEETING_SCHEDULED = "meeting_scheduled"
    CONVERTED = "converted"  # Became customer
    OPTED_OUT = "opted_out"  # Unsubscribed
    BOUNCED = "bounced"  # Email bounced


class OutreachChannel(str, Enum):
    """Supported outreach channels."""

    LINKEDIN = "linkedin"
    EMAIL = "email"


class MessageType(str, Enum):
    """Types of outreach messages."""

    CONNECTION_REQUEST = "connection_request"  # LinkedIn <200 chars
    LINKEDIN_MESSAGE = "linkedin_message"  # LinkedIn DM after connection
    EMAIL_INITIAL = "email_initial"  # Cold email
    EMAIL_FOLLOWUP_1 = "email_followup_1"  # Day 1
    EMAIL_FOLLOWUP_2 = "email_followup_2"  # Day 4
    EMAIL_FOLLOWUP_3 = "email_followup_3"  # Day 8
    EMAIL_FOLLOWUP_4 = "email_followup_4"  # Day 14 (break-up)


class MessageStatus(str, Enum):
    """Status of outreach messages."""

    DRAFT = "draft"  # Generated, not approved
    APPROVED = "approved"  # Approved for sending
    SCHEDULED = "scheduled"  # Scheduled for sending
    SENT = "sent"  # Successfully sent
    FAILED = "failed"  # Send failed
    CANCELLED = "cancelled"  # Cancelled (e.g., prospect replied)


# =============================================================================
# Models
# =============================================================================


class OutreachCampaign(Base):
    """Outreach campaign container."""

    __tablename__ = "outreach_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Configuration
    channels: Mapped[list] = mapped_column(JSON, default=list)  # ["linkedin", "email"]
    sequence_config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Rate Limits
    daily_linkedin_limit: Mapped[int] = mapped_column(Integer, default=20)
    daily_email_limit: Mapped[int] = mapped_column(Integer, default=50)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    prospects: Mapped[list["Prospect"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    templates: Mapped[list["MessageTemplate"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<OutreachCampaign(id={self.id}, name={self.name})>"


class Prospect(Base):
    """Individual prospect/lead being contacted."""

    __tablename__ = "prospects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("outreach_campaigns.id", ondelete="CASCADE")
    )

    # Contact Info
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    linkedin_profile_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Personal Info
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Personalization Data (from research/brand brief)
    personalization_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Stores: pain_points, metrics, insights, value_proposition, icp_type

    # Brand brief reference
    brand_brief_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # State Machine
    status: Mapped[ProspectStatus] = mapped_column(
        SQLEnum(ProspectStatus), default=ProspectStatus.NEW, index=True
    )

    # Tracking
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=datetime.utcnow, nullable=True
    )
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Engagement Scores
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    personalization_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reply_sentiment: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Email status (for deliverability tracking)
    email_status: Mapped[str | None] = mapped_column(String(50), default="valid", nullable=True)
    # Values: valid, bounced, soft_bounced, complained, unsubscribed

    # Sequence tracking
    current_sequence_step: Mapped[int] = mapped_column(Integer, default=0)
    sequence_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    sequence_paused_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sequence_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Scraper enrichment data
    scraper_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    priority_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    company_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decision_maker_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    campaign: Mapped["OutreachCampaign"] = relationship(back_populates="prospects")
    messages: Mapped[list["OutreachMessage"]] = relationship(
        back_populates="prospect", cascade="all, delete-orphan"
    )
    events: Mapped[list["EngagementEvent"]] = relationship(
        back_populates="prospect", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_prospect_campaign_status", "campaign_id", "status"),)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f"<Prospect(id={self.id}, name={self.full_name}, company={self.company})>"


class OutreachMessage(Base):
    """Individual outreach message generated/sent."""

    __tablename__ = "outreach_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prospect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prospects.id", ondelete="CASCADE")
    )

    # Message Details
    channel: Mapped[OutreachChannel] = mapped_column(SQLEnum(OutreachChannel))
    message_type: Mapped[MessageType] = mapped_column(SQLEnum(MessageType))

    # Content
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text)

    # Personalization metadata
    personalization_used: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Stores: pain_points_used, metrics_used, value_prop, personalization_score

    # Template used (for A/B testing)
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("message_templates.id", ondelete="SET NULL"), nullable=True
    )
    variant: Mapped[str | None] = mapped_column(String(10), nullable=True)  # A, B, C

    # Scheduling
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Status
    status: Mapped[MessageStatus] = mapped_column(
        SQLEnum(MessageStatus), default=MessageStatus.DRAFT
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # External IDs
    external_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # SendGrid ID, etc.

    # Tracking
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Engagement tracking (populated by webhooks)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bounce_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    click_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    prospect: Mapped["Prospect"] = relationship(back_populates="messages")
    template: Mapped["MessageTemplate | None"] = relationship()

    __table_args__ = (Index("ix_message_scheduled_status", "scheduled_at", "status"),)

    @property
    def character_count(self) -> int:
        return len(self.content) if self.content else 0

    @property
    def word_count(self) -> int:
        return len(self.content.split()) if self.content else 0

    def __repr__(self):
        return f"<OutreachMessage(id={self.id}, type={self.message_type}, status={self.status})>"


class EngagementEvent(Base):
    """Track engagement events (opens, clicks, replies, connections)."""

    __tablename__ = "engagement_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prospect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prospects.id", ondelete="CASCADE")
    )
    message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("outreach_messages.id", ondelete="SET NULL"), nullable=True
    )

    # Event Details
    event_type: Mapped[str] = mapped_column(
        String(50), index=True
    )  # open, click, reply, connection_accepted, bounce, unsubscribe
    channel: Mapped[OutreachChannel] = mapped_column(SQLEnum(OutreachChannel))

    # Event metadata
    event_metadata: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # IP, user agent, link clicked, etc.

    # Timestamp
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )

    # Relationships
    prospect: Mapped["Prospect"] = relationship(back_populates="events")

    def __repr__(self):
        return f"<EngagementEvent(id={self.id}, type={self.event_type})>"


class MessageTemplate(Base):
    """Reusable message templates with placeholders."""

    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("outreach_campaigns.id", ondelete="CASCADE")
    )

    name: Mapped[str] = mapped_column(String(200))
    channel: Mapped[OutreachChannel] = mapped_column(SQLEnum(OutreachChannel))
    message_type: Mapped[MessageType] = mapped_column(SQLEnum(MessageType))
    language: Mapped[str] = mapped_column(String(10), default="en")  # en, es, pt

    # Content with placeholders: {{first_name}}, {{company}}, etc.
    subject_template: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_template: Mapped[str] = mapped_column(Text)

    # A/B Testing
    variant: Mapped[str] = mapped_column(String(10), default="A")

    # Metadata
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    campaign: Mapped["OutreachCampaign"] = relationship(back_populates="templates")

    def __repr__(self):
        return f"<MessageTemplate(id={self.id}, name={self.name})>"


class DailyQuota(Base):
    """Track daily sending quotas per channel/campaign."""

    __tablename__ = "daily_quotas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)
    channel: Mapped[OutreachChannel] = mapped_column(SQLEnum(OutreachChannel))
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("outreach_campaigns.id", ondelete="CASCADE")
    )

    # Counts
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    limit: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        Index(
            "ix_quota_date_channel_campaign",
            "date",
            "channel",
            "campaign_id",
            unique=True,
        ),
    )

    def __repr__(self):
        return f"<DailyQuota(date={self.date}, channel={self.channel}, sent={self.sent_count}/{self.limit})>"


class Sequence(Base):
    """Custom email sequence configuration."""

    __tablename__ = "sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sequence steps stored as JSON array
    # Each step: {step_number, delay_days, delay_hours, message_type, template_id, skip_if_opened, skip_if_clicked}
    steps: Mapped[list] = mapped_column(JSON, default=list)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=datetime.utcnow, nullable=True
    )

    def __repr__(self):
        return f"<Sequence(id={self.id}, name={self.name}, steps={len(self.steps or [])})>"
