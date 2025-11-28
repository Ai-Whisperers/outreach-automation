"""
Pydantic models for API request/response validation.
"""

from typing import Any

from pydantic import BaseModel, Field, HttpUrl

# =============================================================================
# Project Models
# =============================================================================

class ProjectCreate(BaseModel):
    """Request model for creating a project."""
    name: str = Field(..., min_length=1, max_length=200, description="Project name")
    client: str = Field(..., min_length=1, max_length=100, description="Client name")
    country: str = Field(default="Paraguay", description="Target country")
    language: str = Field(default="es", description="Primary language")
    campaign_type: str = Field(default="integrated", description="Campaign type")


class ProjectResponse(BaseModel):
    """Response model for project data."""
    id: str
    name: str
    client: str
    country: str
    language: str
    status: str
    created_at: str
    updated_at: str | None = None


class ProjectListResponse(BaseModel):
    """Response model for project list."""
    projects: list[ProjectResponse]
    total: int


# =============================================================================
# Brief Models
# =============================================================================

class BriefUpload(BaseModel):
    """Request model for uploading a brief."""
    content: str = Field(
        ...,
        min_length=100,
        max_length=50000,
        description="Brief content in markdown (max 50KB)"
    )


class BriefAnalysis(BaseModel):
    """Response model for brief analysis."""
    main_challenge: str
    context: str
    constraints: list[str]
    success_looks_like: str


class TargetAudience(BaseModel):
    """Target audience extracted from brief."""
    primary: str
    secondary: str | None = None
    age_range: str
    gender: str
    socioeconomic: str
    location: str
    psychographics: list[str]
    behaviors: list[str]
    media_consumption: list[str]


class CreativeDirection(BaseModel):
    """Creative direction suggestion."""
    name: str
    description: str
    tone: str
    visual_style: str
    example_taglines: list[str]


class BriefRequirements(BaseModel):
    """Brand requirements from brief."""
    mandatories: list[str]
    restrictions: list[str]
    tone_of_voice: str
    visual_guidelines: list[str]


class BriefParseResponse(BaseModel):
    """Complete brief parsing response."""
    project_id: str
    challenge: BriefAnalysis
    target: TargetAudience
    directions: list[CreativeDirection]
    requirements: BriefRequirements


# =============================================================================
# Research Models
# =============================================================================

class ResearchSource(BaseModel):
    """Model for a research source."""
    url: HttpUrl | None = None
    title: str = Field(..., max_length=500, description="Source title")
    content: str | None = Field(default=None, max_length=100000, description="Source content (max 100KB)")
    type: str = Field(default="web", max_length=50, description="Source type: web, report, interview, etc.")
    category: str = Field(..., max_length=100, description="Research category")


class ResearchSummary(BaseModel):
    """Summarized research content."""
    title: str
    summary: str
    key_points: list[str]
    statistics: list[dict[str, Any]]
    relevance_score: float
    source_type: str


class ResearchAddRequest(BaseModel):
    """Request to add research to project."""
    sources: list[ResearchSource] = Field(..., max_length=50, description="Research sources (max 50)")


class ResearchAddResponse(BaseModel):
    """Response after adding research."""
    project_id: str
    added_count: int
    files_created: list[str]
    sources_tracked: int


# =============================================================================
# Synthesis Models
# =============================================================================

class MarketSnapshot(BaseModel):
    """Market snapshot data."""
    size: str
    growth: str
    brand_share: str
    main_competitor: str


class Target30Seconds(BaseModel):
    """Quick target description."""
    who: str
    age: str
    motivation: str
    barrier: str
    media: str


class KeyInsight(BaseModel):
    """Problem-reality-opportunity insight."""
    problem: str
    reality: str
    opportunity: str


class QuickReference(BaseModel):
    """Quick reference for brainstorming."""
    challenge_one_liner: str
    market_snapshot: MarketSnapshot
    target_30_seconds: Target30Seconds
    key_insights: list[KeyInsight]
    dos: list[str]
    donts: list[str]
    brainstorm_questions: list[str]


class SynthesizeRequest(BaseModel):
    """Request to synthesize research."""
    include_quick_reference: bool = True
    include_insights: bool = True
    include_dos_donts: bool = True


class SynthesizeResponse(BaseModel):
    """Response from synthesis."""
    project_id: str
    quick_reference: QuickReference | None = None
    files_created: list[str]


# =============================================================================
# Ideas Models
# =============================================================================

class IdeaGenerateRequest(BaseModel):
    """Request to generate ideas."""
    num_ideas: int = Field(default=25, ge=1, le=100)
    batch_size: int = Field(default=5, ge=1, le=10)
    creative_directions: list[str] | None = None


class Idea(BaseModel):
    """Simple idea model for agents."""
    title: str
    description: str
    rationale: str
    score: float = 0.0


class IdeaConcept(BaseModel):
    """Basic idea concept."""
    number: int
    title: str
    concept: str
    insight: str
    formats: list[str]


class IdeaGenerateResponse(BaseModel):
    """Response from idea generation."""
    project_id: str
    ideas_generated: int
    concepts: list[IdeaConcept]
    files_created: list[str] = []


class IdeaExpandRequest(BaseModel):
    """Request to expand an idea."""
    idea_number: int


class IdeaScores(BaseModel):
    """Scores for an idea."""
    diferenciacion: float = Field(ge=1, le=10)
    relevancia_cultural: float = Field(ge=1, le=10)
    claridad_insight: float = Field(ge=1, le=10)
    ejecutabilidad: float = Field(ge=1, le=10)
    potencial_viral: float = Field(ge=1, le=10)
    memorabilidad: float = Field(ge=1, le=10)
    versatilidad: float = Field(ge=1, le=10)
    alineacion_marca: float = Field(ge=1, le=10)
    potencial_pr: float = Field(ge=1, le=10)
    escalabilidad: float = Field(ge=1, le=10)


class IdeaExpanded(BaseModel):
    """Fully expanded idea."""
    number: int
    title: str
    concept: str
    insight: str
    execution: dict[str, str]
    scores: IdeaScores
    overall_score: float
    tier: str
    strengths: list[str]
    weaknesses: list[str]
    recommendation: str


class IdeaExpandResponse(BaseModel):
    """Response from idea expansion."""
    project_id: str
    idea: IdeaExpanded
    file_path: str


class IdeaScoreRequest(BaseModel):
    """Request to score all ideas."""
    recalculate: bool = False


class IdeaSummary(BaseModel):
    """Summary info for an idea."""
    number: int
    title: str
    overall_score: float
    tier: str


class IdeaScoreResponse(BaseModel):
    """Response from scoring."""
    project_id: str
    total_ideas: int
    tier_distribution: dict[str, int]
    top_ideas: list[IdeaSummary]
    summary_file: str


# =============================================================================
# Export Models
# =============================================================================

class ExportRequest(BaseModel):
    """Request for export."""
    format: str = Field(..., pattern="^(pdf|pptx)$")
    include_research: bool = True
    include_all_ideas: bool = False
    top_ideas_count: int = Field(default=10, ge=1, le=50)


class ExportResponse(BaseModel):
    """Response from export."""
    project_id: str
    format: str
    file_path: str
    file_size: int
    pages: int | None = None


# =============================================================================
# Quality Models
# =============================================================================

class QualityValidation(BaseModel):
    """Quality validation result."""
    scores: dict[str, float]
    overall: float
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]


class CulturalValidation(BaseModel):
    """Cultural validation result."""
    cultural_score: float
    positives: list[str]
    concerns: list[str]
    suggestions: list[str]
    approved: bool
