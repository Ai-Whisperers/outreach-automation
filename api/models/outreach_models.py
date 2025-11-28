"""
Pydantic models for outreach API request/response validation.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


# =============================================================================
# Enums as Literals for API
# =============================================================================

ProspectStatusType = Literal[
    "new",
    "researched",
    "scheduled",
    "contacted",
    "connected",
    "engaged",
    "replied",
    "meeting_scheduled",
    "converted",
    "opted_out",
    "bounced",
]

ChannelType = Literal["linkedin", "email"]

MessageTypeType = Literal[
    "connection_request",
    "linkedin_message",
    "email_initial",
    "email_followup_1",
    "email_followup_2",
    "email_followup_3",
    "email_followup_4",
]

ICPType = Literal["solopreneur", "sme", "enterprise"]

LanguageType = Literal["en", "es", "pt"]


# =============================================================================
# Campaign Models
# =============================================================================


class CampaignCreate(BaseModel):
    """Request model for creating an outreach campaign."""

    name: str = Field(..., min_length=1, max_length=200, description="Campaign name")
    description: str | None = Field(
        default=None, max_length=2000, description="Campaign description"
    )
    channels: list[ChannelType] = Field(
        default=["linkedin", "email"], description="Outreach channels"
    )
    daily_linkedin_limit: int = Field(
        default=20, ge=1, le=25, description="Daily LinkedIn connection limit"
    )
    daily_email_limit: int = Field(
        default=50, ge=1, le=200, description="Daily email limit"
    )


class CampaignUpdate(BaseModel):
    """Request model for updating a campaign."""

    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    daily_linkedin_limit: int | None = Field(default=None, ge=1, le=25)
    daily_email_limit: int | None = Field(default=None, ge=1, le=200)
    is_active: bool | None = None


class CampaignResponse(BaseModel):
    """Response model for campaign data."""

    id: int
    name: str
    description: str | None
    channels: list[str]
    daily_linkedin_limit: int
    daily_email_limit: int
    is_active: bool
    prospect_count: int = 0
    message_count: int = 0
    created_at: str
    started_at: str | None = None
    paused_at: str | None = None


class CampaignListResponse(BaseModel):
    """Response model for campaign list."""

    campaigns: list[CampaignResponse]
    total: int


class CampaignAnalytics(BaseModel):
    """Response model for campaign analytics."""

    campaign_id: int
    campaign_name: str
    total_prospects: int = 0
    messages_sent: int = 0
    messages_opened: int = 0
    messages_clicked: int = 0
    messages_replied: int = 0
    connections_sent: int = 0
    connections_accepted: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    reply_rate: float = 0.0
    connection_rate: float = 0.0


# =============================================================================
# Prospect Models
# =============================================================================


class ProspectCreate(BaseModel):
    """Request model for creating a single prospect."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr | None = None
    linkedin_url: str | None = Field(default=None, max_length=500)
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    pain_points: list[str] | None = Field(default=None, max_length=10)
    metrics: dict | None = None

    @field_validator("linkedin_url")
    @classmethod
    def validate_linkedin_url(cls, v):
        if v and "linkedin.com" not in v.lower():
            raise ValueError("Must be a LinkedIn URL")
        return v


class ProspectCSVRow(BaseModel):
    """Model for a single row in CSV import."""

    first_name: str
    last_name: str
    email: str | None = None
    linkedin_url: str | None = None
    company: str | None = None
    title: str | None = None
    industry: str | None = None
    location: str | None = None
    pain_points: str | None = None  # Comma-separated in CSV
    metrics: str | None = None  # JSON string in CSV


class ProspectBulkImport(BaseModel):
    """Request model for bulk CSV import."""

    csv_content: str = Field(
        ..., min_length=10, description="CSV content (raw or base64 encoded)"
    )
    skip_duplicates: bool = Field(
        default=True, description="Skip prospects with existing email/LinkedIn URL"
    )
    auto_link_brand_briefs: bool = Field(
        default=True, description="Auto-link to brand briefs by company name"
    )


class ProspectBulkImportResponse(BaseModel):
    """Response from bulk import."""

    campaign_id: int
    added_count: int
    duplicates_skipped: int
    invalid_skipped: int
    errors: list[str] = []


class ProspectUpdate(BaseModel):
    """Request model for updating a prospect."""

    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    linkedin_url: str | None = Field(default=None, max_length=500)
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=100)
    status: ProspectStatusType | None = None
    personalization_data: dict | None = None


class ProspectResponse(BaseModel):
    """Response model for prospect data."""

    id: int
    campaign_id: int
    full_name: str
    first_name: str
    last_name: str
    email: str | None
    linkedin_url: str | None
    company: str | None
    title: str | None
    industry: str | None
    location: str | None
    status: str
    engagement_score: float
    personalization_score: float | None
    message_count: int = 0
    last_contacted_at: str | None
    created_at: str


class ProspectListResponse(BaseModel):
    """Response model for prospect list."""

    prospects: list[ProspectResponse]
    total: int
    page: int
    per_page: int


class ProspectImportResult(BaseModel):
    """Result of prospect import operation."""

    total_processed: int = 0
    imported: int = 0
    skipped: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)


class ProspectTimeline(BaseModel):
    """Timeline event for a prospect."""

    timestamp: str
    event_type: str
    channel: str | None
    details: dict | None


class ProspectTimelineResponse(BaseModel):
    """Full prospect timeline."""

    prospect_id: int
    prospect_name: str
    company: str | None
    status: str
    events: list[ProspectTimeline]


# =============================================================================
# Message Models
# =============================================================================


class MessageGenerateRequest(BaseModel):
    """Request to generate messages for prospects."""

    message_types: list[MessageTypeType] = Field(
        default=["connection_request", "email_initial"],
        description="Types of messages to generate",
    )
    language: LanguageType = Field(default="en", description="Target language")
    icp_override: ICPType | None = Field(
        default=None, description="Override ICP detection"
    )
    prospect_ids: list[int] | None = Field(
        default=None, description="Specific prospect IDs (None = all pending)"
    )


class MessageGenerateForProspectRequest(BaseModel):
    """Request to generate messages for a single prospect."""

    message_types: list[MessageTypeType] = Field(
        default=["connection_request", "email_initial"]
    )
    language: LanguageType = Field(default="en")
    icp_override: ICPType | None = None
    regenerate: bool = Field(
        default=False, description="Regenerate even if messages exist"
    )


class LinkedInConnectionMessage(BaseModel):
    """Generated LinkedIn connection request."""

    message: str = Field(..., max_length=200)
    character_count: int
    personalization_elements: list[str]
    validation_passed: bool


class LinkedInMessage(BaseModel):
    """Generated LinkedIn DM."""

    message: str
    word_count: int
    personalization_elements: list[str]
    call_to_action: str


class EmailMessage(BaseModel):
    """Generated email message."""

    subject: str = Field(..., max_length=100)
    body: str
    word_count: int
    personalization_score: float
    personalization_elements: list[str]


class FollowUpSequence(BaseModel):
    """4-part follow-up email sequence."""

    follow_up_1: EmailMessage  # Day 1
    follow_up_2: EmailMessage  # Day 4
    follow_up_3: EmailMessage  # Day 8
    follow_up_4: EmailMessage  # Day 14 (break-up)


class MessageGenerateResponse(BaseModel):
    """Response from message generation."""

    prospect_id: int
    prospect_name: str
    company: str | None
    icp_type: str
    language: str
    linkedin_connection: LinkedInConnectionMessage | None = None
    linkedin_message: LinkedInMessage | None = None
    cold_email: EmailMessage | None = None
    follow_up_sequence: FollowUpSequence | None = None
    messages_created: int
    generation_time_ms: int


class MessageBatchGenerateResponse(BaseModel):
    """Response from batch message generation."""

    campaign_id: int
    prospects_processed: int
    messages_generated: int
    errors: list[str] = []


class MessageResponse(BaseModel):
    """Response model for a single message."""

    id: int
    prospect_id: int
    prospect_name: str
    company: str | None
    channel: str
    message_type: str
    subject: str | None
    content: str
    character_count: int
    word_count: int
    personalization_score: float | None
    status: str
    scheduled_at: str | None
    sent_at: str | None
    created_at: str


class MessageListResponse(BaseModel):
    """Response model for message list."""

    messages: list[MessageResponse]
    total: int


class MessagePreviewRequest(BaseModel):
    """Request to preview a message without saving."""

    prospect_id: int
    message_type: MessageTypeType
    language: LanguageType = "en"
    icp_override: ICPType | None = None


class MessageEditRequest(BaseModel):
    """Request to edit a message."""

    subject: str | None = Field(default=None, max_length=500)
    content: str | None = None


class MessageApproveRequest(BaseModel):
    """Request to approve messages for sending."""

    message_ids: list[int]


class MessageApproveResponse(BaseModel):
    """Response from message approval."""

    approved_count: int
    failed_count: int
    errors: list[str] = []


# =============================================================================
# Template Models
# =============================================================================


class TemplateCreate(BaseModel):
    """Request to create a message template."""

    name: str = Field(..., max_length=200)
    channel: ChannelType
    message_type: MessageTypeType
    language: LanguageType = "en"
    subject_template: str | None = Field(default=None, max_length=500)
    content_template: str = Field(..., min_length=10)
    variant: str = Field(default="A", max_length=10)


class TemplateUpdate(BaseModel):
    """Request to update a template."""

    name: str | None = Field(default=None, max_length=200)
    subject_template: str | None = Field(default=None, max_length=500)
    content_template: str | None = None
    is_active: bool | None = None


class TemplateResponse(BaseModel):
    """Response model for template."""

    id: int
    campaign_id: int
    name: str
    channel: str
    message_type: str
    language: str
    subject_template: str | None
    content_template: str
    variant: str
    is_active: bool
    created_at: str


class TemplateListResponse(BaseModel):
    """Response model for template list."""

    templates: list[TemplateResponse]
    total: int


# =============================================================================
# Outreach Execution Models
# =============================================================================


class OutreachStartRequest(BaseModel):
    """Request to start outreach execution."""

    channels: list[ChannelType] | None = Field(
        default=None, description="Channels to activate (None = all)"
    )
    prospect_ids: list[int] | None = Field(
        default=None, description="Specific prospects (None = all approved)"
    )


class OutreachPauseRequest(BaseModel):
    """Request to pause outreach."""

    cancel_scheduled: bool = Field(
        default=False, description="Cancel already scheduled messages"
    )


class OutreachStatusResponse(BaseModel):
    """Response for outreach status."""

    campaign_id: int
    is_active: bool
    started_at: str | None
    paused_at: str | None
    today_linkedin_sent: int
    today_linkedin_remaining: int
    today_email_sent: int
    today_email_remaining: int
    total_scheduled: int
    total_sent: int


# =============================================================================
# Analytics Models
# =============================================================================


class DailyMetrics(BaseModel):
    """Metrics for a single day."""

    date: str
    linkedin_sent: int
    email_sent: int
    connections_accepted: int
    emails_opened: int
    emails_clicked: int
    replies_received: int


class FunnelStage(BaseModel):
    """Single funnel stage."""

    stage: str
    count: int
    percentage: float


class AnalyticsDashboard(BaseModel):
    """Full analytics dashboard."""

    campaign_id: int
    period: str  # 7d, 30d, all

    # Volume metrics
    total_prospects: int
    total_sent: int
    linkedin_sent: int
    email_sent: int

    # Engagement metrics
    connections_accepted: int
    connection_rate: float
    emails_opened: int
    open_rate: float
    emails_clicked: int
    click_rate: float
    replies_received: int
    reply_rate: float

    # Pipeline
    prospects_by_status: dict[str, int]
    funnel: list[FunnelStage]

    # Trends
    daily_trends: list[DailyMetrics]


class ABTestResult(BaseModel):
    """A/B test results for a template variant."""

    variant: str
    sent_count: int
    open_rate: float
    click_rate: float
    reply_rate: float
    winner: bool


class ABTestResponse(BaseModel):
    """A/B test comparison."""

    message_type: str
    variants: list[ABTestResult]
    statistical_significance: float
    recommendation: str


# =============================================================================
# Webhook Models
# =============================================================================


class SendGridEvent(BaseModel):
    """SendGrid webhook event."""

    event: str  # delivered, open, click, bounce, etc.
    email: str | None = None
    timestamp: int | None = None
    sg_message_id: str | None = None
    url: str | None = None  # For click events
    useragent: str | None = None
    ip: str | None = None


class WebhookResponse(BaseModel):
    """Response for webhook processing."""

    status: str
    events_processed: int


# =============================================================================
# Additional Missing Models
# =============================================================================


class MessageValidationResult(BaseModel):
    """Result of message validation."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    character_count: int = 0
    word_count: int = 0


class ScheduleRequest(BaseModel):
    """Request to schedule message sending."""

    campaign_id: int
    schedule_time: str | None = None  # ISO datetime or None for immediate
    batch_size: int = Field(default=50, ge=1, le=200)


class ScheduleResponse(BaseModel):
    """Response from scheduling messages."""

    scheduled_count: int
    campaign_id: int
    scheduled_for: str


class SendRequest(BaseModel):
    """Request to send specific message."""

    message_id: int


class SendResponse(BaseModel):
    """Response from sending a message."""

    success: bool
    message_id: int
    external_id: str | None = None
    error: str | None = None


class QuotaStatus(BaseModel):
    """Current quota status for a campaign/channel."""

    campaign_id: int
    channel: str
    daily_limit: int
    used_today: int
    remaining: int
    reset_at: str
