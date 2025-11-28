"""
Pydantic models for API request/response validation.
"""

# Import from the parent models.py file (legacy models)
import sys
from pathlib import Path

# Add parent directory to import from api/models.py
_parent = Path(__file__).parent.parent / "models.py"
if _parent.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("legacy_models", _parent)
    _legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_legacy)

    # Re-export ALL legacy models
    ProjectCreate = _legacy.ProjectCreate
    ProjectResponse = _legacy.ProjectResponse
    ProjectListResponse = _legacy.ProjectListResponse
    BriefUpload = _legacy.BriefUpload
    BriefAnalysis = _legacy.BriefAnalysis
    TargetAudience = _legacy.TargetAudience
    CreativeDirection = _legacy.CreativeDirection
    BriefRequirements = _legacy.BriefRequirements
    BriefParseResponse = _legacy.BriefParseResponse
    ResearchSource = _legacy.ResearchSource
    ResearchSummary = _legacy.ResearchSummary
    ResearchAddRequest = _legacy.ResearchAddRequest
    ResearchAddResponse = _legacy.ResearchAddResponse
    MarketSnapshot = _legacy.MarketSnapshot
    Target30Seconds = _legacy.Target30Seconds
    KeyInsight = _legacy.KeyInsight
    QuickReference = _legacy.QuickReference
    SynthesizeRequest = _legacy.SynthesizeRequest
    SynthesizeResponse = _legacy.SynthesizeResponse
    IdeaGenerateRequest = _legacy.IdeaGenerateRequest
    Idea = _legacy.Idea
    IdeaConcept = _legacy.IdeaConcept
    IdeaGenerateResponse = _legacy.IdeaGenerateResponse
    IdeaExpandRequest = _legacy.IdeaExpandRequest
    IdeaScores = _legacy.IdeaScores
    IdeaExpanded = _legacy.IdeaExpanded
    IdeaExpandResponse = _legacy.IdeaExpandResponse
    IdeaScoreRequest = _legacy.IdeaScoreRequest
    IdeaSummary = _legacy.IdeaSummary
    IdeaScoreResponse = _legacy.IdeaScoreResponse
    ExportRequest = _legacy.ExportRequest
    ExportResponse = _legacy.ExportResponse
    QualityValidation = _legacy.QualityValidation
    CulturalValidation = _legacy.CulturalValidation

from .outreach_models import (
    # Campaign
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignListResponse,
    # Prospect
    ProspectCreate,
    ProspectCSVRow,
    ProspectBulkImport,
    ProspectBulkImportResponse,
    ProspectUpdate,
    ProspectResponse,
    ProspectListResponse,
    ProspectTimeline,
    ProspectTimelineResponse,
    # Message
    MessageGenerateRequest,
    MessageGenerateForProspectRequest,
    LinkedInConnectionMessage,
    LinkedInMessage,
    EmailMessage,
    FollowUpSequence,
    MessageGenerateResponse,
    MessageBatchGenerateResponse,
    MessageResponse,
    MessageListResponse,
    MessagePreviewRequest,
    MessageEditRequest,
    MessageApproveRequest,
    MessageApproveResponse,
    # Template
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
    TemplateListResponse,
    # Outreach
    OutreachStartRequest,
    OutreachPauseRequest,
    OutreachStatusResponse,
    # Analytics
    DailyMetrics,
    FunnelStage,
    AnalyticsDashboard,
    ABTestResult,
    ABTestResponse,
    # Webhook
    SendGridEvent,
    WebhookResponse,
    # Type aliases
    ProspectStatusType,
    ChannelType,
    MessageTypeType,
    ICPType,
    LanguageType,
)

__all__ = [
    # Campaign
    "CampaignCreate",
    "CampaignUpdate",
    "CampaignResponse",
    "CampaignListResponse",
    # Prospect
    "ProspectCreate",
    "ProspectCSVRow",
    "ProspectBulkImport",
    "ProspectBulkImportResponse",
    "ProspectUpdate",
    "ProspectResponse",
    "ProspectListResponse",
    "ProspectTimeline",
    "ProspectTimelineResponse",
    # Message
    "MessageGenerateRequest",
    "MessageGenerateForProspectRequest",
    "LinkedInConnectionMessage",
    "LinkedInMessage",
    "EmailMessage",
    "FollowUpSequence",
    "MessageGenerateResponse",
    "MessageBatchGenerateResponse",
    "MessageResponse",
    "MessageListResponse",
    "MessagePreviewRequest",
    "MessageEditRequest",
    "MessageApproveRequest",
    "MessageApproveResponse",
    # Template
    "TemplateCreate",
    "TemplateUpdate",
    "TemplateResponse",
    "TemplateListResponse",
    # Outreach
    "OutreachStartRequest",
    "OutreachPauseRequest",
    "OutreachStatusResponse",
    # Analytics
    "DailyMetrics",
    "FunnelStage",
    "AnalyticsDashboard",
    "ABTestResult",
    "ABTestResponse",
    # Webhook
    "SendGridEvent",
    "WebhookResponse",
    # Type aliases
    "ProspectStatusType",
    "ChannelType",
    "MessageTypeType",
    "ICPType",
    "LanguageType",
    # Legacy models from api/models.py
    "ProjectCreate",
    "ProjectResponse",
    "ProjectListResponse",
    "BriefUpload",
    "BriefAnalysis",
    "TargetAudience",
    "CreativeDirection",
    "BriefRequirements",
    "BriefParseResponse",
    "ResearchSource",
    "ResearchSummary",
    "ResearchAddRequest",
    "ResearchAddResponse",
    "MarketSnapshot",
    "Target30Seconds",
    "KeyInsight",
    "QuickReference",
    "SynthesizeRequest",
    "SynthesizeResponse",
    "IdeaGenerateRequest",
    "Idea",
    "IdeaConcept",
    "IdeaGenerateResponse",
    "IdeaExpandRequest",
    "IdeaScores",
    "IdeaExpanded",
    "IdeaExpandResponse",
    "IdeaScoreRequest",
    "IdeaSummary",
    "IdeaScoreResponse",
    "ExportRequest",
    "ExportResponse",
    "QualityValidation",
    "CulturalValidation",
]
