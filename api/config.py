"""
Configuration management for Campaign Generator API.

Uses Pydantic Settings for environment variable loading and validation,
merging with YAML configuration for project-specific settings.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# =============================================================================
# Nested Configuration Models
# =============================================================================


class ProjectSettings(BaseModel):
    """Project-specific defaults."""

    default_country: str = "Paraguay"
    default_language: str = "es"
    default_type: str = "digital"
    default_year: int = 2025
    num_ideas: int = 25
    ideas_per_batch: int = 5


class ResearchCategory(BaseModel):
    """Research category definition."""

    id: str
    name: str
    files: list[str]


class ResearchSettings(BaseModel):
    """Research configuration."""

    categories: list[ResearchCategory] = []


class ScoringCriterion(BaseModel):
    """Single scoring criterion."""

    name: str
    weight: float = 1.0
    description: str = ""


class ScoringThresholds(BaseModel):
    """Scoring thresholds."""

    very_high: float = 90
    high: float = 80
    medium: float = 70
    needs_work: float = 60


class ScoringSettings(BaseModel):
    """Scoring configuration."""

    criteria: list[ScoringCriterion] = []
    thresholds: ScoringThresholds = Field(default_factory=ScoringThresholds)


class AIProviderSettings(BaseModel):
    """Settings for a specific AI provider."""

    model: str
    max_tokens: int = 4096
    temperature: float = 0.7


class AISettings(BaseModel):
    """AI configuration."""

    primary: str = "anthropic"
    fallback: str = "openai"
    anthropic: AIProviderSettings | None = None
    openai: AIProviderSettings | None = None
    gemini: AIProviderSettings | None = None
    groq: AIProviderSettings | None = None


class ExportFormatSettings(BaseModel):
    """Settings for export formats."""

    font_family: str = "Helvetica"
    font_size: int = 11
    margin: int = 72
    include_cover: bool = True
    include_toc: bool = True
    template: str = "default"
    include_notes: bool = True


class ExportSettings(BaseModel):
    """Export configuration."""

    pdf: ExportFormatSettings | None = None
    pptx: ExportFormatSettings | None = None


# =============================================================================
# Main Settings
# =============================================================================


class Settings(BaseSettings):
    """
    Unified application settings.
    Loads from .env (env vars) and config/default.yaml (YAML).
    Env vars take precedence over YAML.
    """

    # API Keys (Env vars)
    anthropic_api_key: str | None = Field(default=None, description="Anthropic Claude API key")
    openai_api_key: str = Field(default="", description="OpenAI API key (fallback)")
    gemini_api_key: str | None = Field(default=None, description="Google Gemini API key")
    groq_api_key: str | None = Field(default=None, description="Groq API key")
    tavily_api_key: str | None = Field(default=None, description="Tavily API key")

    # Application (Env vars)
    projects_dir: Path = Field(default=Path("./projects"), description="Projects directory")
    python_api_url: str = Field(default="http://localhost:8000", description="API URL")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment name")

    # Database (Env vars)
    database_url: str = Field(
        default="sqlite+aiosqlite:///./campaign_generator.db",
        description="Database URL (PostgreSQL or SQLite)",
    )

    # Redis (Env vars)
    redis_enabled: bool = Field(default=False, description="Enable Redis caching for LLM responses")
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis URL for Celery and LLM caching"
    )
    redis_ttl: int = Field(default=3600, description="Redis cache TTL in seconds (1 hour)")

    # Langfuse Configuration
    langfuse_public_key: str | None = Field(default=None, description="Langfuse Public Key")
    langfuse_secret_key: str | None = Field(default=None, description="Langfuse Secret Key")
    langfuse_host: str | None = Field(
        default="https://cloud.langfuse.com", description="Langfuse Host"
    )

    # Optional (Env vars)
    slack_webhook: str | None = Field(default=None, description="Slack webhook for alerts")

    # Security (Env vars)
    api_key: str = Field(default="", description="API key for authentication (empty = disabled)")
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:8080",
        description="Comma-separated list of allowed CORS origins",
    )
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Max requests per window")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")

    # Outreach Configuration (Env vars)
    sendgrid_api_key: str | None = Field(default=None, description="SendGrid API key for email sending")
    email_from_address: str = Field(default="hello@ai-whisperers.com", description="Default from email")
    email_from_name: str = Field(default="AI Whisperers", description="Default from name")
    email_tracking_domain: str | None = Field(default=None, description="Custom tracking domain")

    # LinkedIn Configuration
    linkedin_cookies_path: str = Field(default="./linkedin_cookies.json", description="Path to LinkedIn cookies")
    linkedin_headless: bool = Field(default=True, description="Run LinkedIn browser headless")
    linkedin_daily_limit: int = Field(default=20, description="Daily LinkedIn connection limit")
    linkedin_action_delay_min: float = Field(default=2.0, description="Min delay between actions (seconds)")
    linkedin_action_delay_max: float = Field(default=5.0, description="Max delay between actions (seconds)")

    # Brand Briefs
    brand_briefs_dir: str = Field(default="./brand-briefs", description="Directory for brand brief files")

    # Caching (Env vars)
    cache_enabled: bool = Field(default=True, description="Enable AI response caching")
    cache_ttl_memory: int = Field(default=1800, description="Memory cache TTL in seconds (30 min)")
    cache_ttl_file: int = Field(default=86400, description="File cache TTL in seconds (24 hours)")

    # LangGraph v2 Feature Flags (Env vars)
    use_langgraph_v2: bool = Field(
        default=False, description="Enable LangGraph v2 (parallel research)"
    )
    enable_parallel_research: bool = Field(
        default=False, description="Enable parallel research nodes"
    )

    # LangSmith Observability (Env vars)
    langchain_tracing_v2: bool = Field(default=False, description="Enable LangSmith tracing")
    langchain_api_key: str = Field(default="", description="LangSmith API key")
    langchain_project: str = Field(
        default="maga-campaign-generator", description="LangSmith project name"
    )

    # YAML Configuration Sections
    project: ProjectSettings = Field(default_factory=ProjectSettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    ai: AISettings = Field(default_factory=AISettings)
    export: ExportSettings = Field(default_factory=ExportSettings)

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        yaml_file=Path(__file__).parent.parent / "config" / "default.yaml",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    @field_validator("projects_dir", mode="before")
    @classmethod
    def validate_projects_dir(cls, v):
        """Ensure projects directory exists."""
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()

    # Helper methods for backward compatibility logic
    def get_tier_for_score(self, score: float) -> str:
        """Get tier classification for a score."""
        t = self.scoring.thresholds
        if score >= t.very_high:
            return "very_high"
        elif score >= t.high:
            return "high"
        elif score >= t.medium:
            return "medium"
        elif score >= t.needs_work:
            return "low"
        else:
            return "very_low"

    def calculate_weighted_score(self, scores: dict[str, float]) -> float:
        """Calculate weighted average score."""
        total_weight = 0
        weighted_sum = 0

        for criterion in self.scoring.criteria:
            if criterion.name in scores:
                weighted_sum += scores[criterion.name] * criterion.weight
                total_weight += criterion.weight

        if total_weight == 0:
            return 0

        return weighted_sum / total_weight


# =============================================================================
# Singleton Access
# =============================================================================


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.
    """
    return Settings()


# Deprecated: For backward compatibility during migration
def get_project_config() -> Settings:
    """
    Deprecated: Use get_settings() instead.
    Returns the same Settings object.
    """
    return get_settings()
