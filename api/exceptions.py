"""
Custom exceptions for Campaign Generator API.

All application-specific exceptions inherit from CampaignGeneratorError
for consistent error handling throughout the system.
"""

from typing import Any


class CampaignGeneratorError(Exception):
    """Base exception for all Campaign Generator errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        details: dict[str, Any] | None = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details
        }


# =============================================================================
# Configuration Errors
# =============================================================================

class ConfigurationError(CampaignGeneratorError):
    """Raised when there's an issue with configuration."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details=details
        )


class MissingAPIKeyError(ConfigurationError):
    """Raised when a required API key is missing."""

    def __init__(self, provider: str):
        super().__init__(
            message=f"API key for {provider} is not configured",
            details={"provider": provider}
        )


# =============================================================================
# AI Provider Errors
# =============================================================================

class AIProviderError(CampaignGeneratorError):
    """Base exception for AI provider errors."""

    def __init__(
        self,
        message: str,
        provider: str,
        error_code: str = "AI_PROVIDER_ERROR",
        details: dict | None = None
    ):
        details = details or {}
        details["provider"] = provider
        super().__init__(
            message=message,
            error_code=error_code,
            details=details
        )


class AIRateLimitError(AIProviderError):
    """Raised when AI provider rate limit is exceeded."""

    def __init__(self, provider: str, retry_after: int | None = None):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(
            message=f"Rate limit exceeded for {provider}",
            provider=provider,
            error_code="AI_RATE_LIMIT",
            details=details
        )


class AIResponseError(AIProviderError):
    """Raised when AI provider returns invalid response."""

    def __init__(self, provider: str, reason: str):
        super().__init__(
            message=f"Invalid response from {provider}: {reason}",
            provider=provider,
            error_code="AI_RESPONSE_ERROR",
            details={"reason": reason}
        )


class AITimeoutError(AIProviderError):
    """Raised when AI provider request times out."""

    def __init__(self, provider: str, timeout_seconds: int):
        super().__init__(
            message=f"Request to {provider} timed out after {timeout_seconds}s",
            provider=provider,
            error_code="AI_TIMEOUT",
            details={"timeout_seconds": timeout_seconds}
        )


# =============================================================================
# Project Errors
# =============================================================================

class ProjectError(CampaignGeneratorError):
    """Base exception for project-related errors."""
    pass


class ProjectNotFoundError(ProjectError):
    """Raised when a project cannot be found."""

    def __init__(self, project_id: str):
        super().__init__(
            message=f"Project not found: {project_id}",
            error_code="PROJECT_NOT_FOUND",
            details={"project_id": project_id}
        )


class ProjectExistsError(ProjectError):
    """Raised when attempting to create a project that already exists."""

    def __init__(self, project_id: str):
        super().__init__(
            message=f"Project already exists: {project_id}",
            error_code="PROJECT_EXISTS",
            details={"project_id": project_id}
        )


class ProjectValidationError(ProjectError):
    """Raised when project data fails validation."""

    def __init__(self, message: str, validation_errors: list[dict]):
        super().__init__(
            message=message,
            error_code="PROJECT_VALIDATION_ERROR",
            details={"validation_errors": validation_errors}
        )


# =============================================================================
# Brief Errors
# =============================================================================

class BriefError(CampaignGeneratorError):
    """Base exception for brief-related errors."""
    pass


class BriefParsingError(BriefError):
    """Raised when brief cannot be parsed."""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Failed to parse brief: {reason}",
            error_code="BRIEF_PARSING_ERROR",
            details={"reason": reason}
        )


class IncompleteBriefError(BriefError):
    """Raised when brief is missing required information."""

    def __init__(self, missing_fields: list[str]):
        super().__init__(
            message=f"Brief is missing required fields: {', '.join(missing_fields)}",
            error_code="INCOMPLETE_BRIEF",
            details={"missing_fields": missing_fields}
        )


# =============================================================================
# Research Errors
# =============================================================================

class ResearchError(CampaignGeneratorError):
    """Base exception for research-related errors."""
    pass


class SourceFetchError(ResearchError):
    """Raised when a source cannot be fetched."""

    def __init__(self, url: str, reason: str):
        super().__init__(
            message=f"Failed to fetch source: {reason}",
            error_code="SOURCE_FETCH_ERROR",
            details={"url": url, "reason": reason}
        )


class ContentExtractionError(ResearchError):
    """Raised when content cannot be extracted from source."""

    def __init__(self, url: str, reason: str):
        super().__init__(
            message=f"Failed to extract content: {reason}",
            error_code="CONTENT_EXTRACTION_ERROR",
            details={"url": url, "reason": reason}
        )


# =============================================================================
# Idea Generation Errors
# =============================================================================

class IdeaGenerationError(CampaignGeneratorError):
    """Base exception for idea generation errors."""
    pass


class InsufficientDataError(IdeaGenerationError):
    """Raised when there's not enough data to generate ideas."""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Insufficient data for idea generation: {reason}",
            error_code="INSUFFICIENT_DATA",
            details={"reason": reason}
        )


class ScoringError(IdeaGenerationError):
    """Raised when idea scoring fails."""

    def __init__(self, idea_id: str, reason: str):
        super().__init__(
            message=f"Failed to score idea: {reason}",
            error_code="SCORING_ERROR",
            details={"idea_id": idea_id, "reason": reason}
        )


# =============================================================================
# Export Errors
# =============================================================================

class ExportError(CampaignGeneratorError):
    """Base exception for export-related errors."""
    pass


class PDFGenerationError(ExportError):
    """Raised when PDF generation fails."""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Failed to generate PDF: {reason}",
            error_code="PDF_GENERATION_ERROR",
            details={"reason": reason}
        )


class PowerPointGenerationError(ExportError):
    """Raised when PowerPoint generation fails."""

    def __init__(self, reason: str):
        super().__init__(
            message=f"Failed to generate PowerPoint: {reason}",
            error_code="PPTX_GENERATION_ERROR",
            details={"reason": reason}
        )


class TemplateRenderError(ExportError):
    """Raised when template rendering fails."""

    def __init__(self, template_name: str, reason: str):
        super().__init__(
            message=f"Failed to render template '{template_name}': {reason}",
            error_code="TEMPLATE_RENDER_ERROR",
            details={"template": template_name, "reason": reason}
        )


# =============================================================================
# File System Errors
# =============================================================================

class FileSystemError(CampaignGeneratorError):
    """Base exception for file system errors."""
    pass


class FileNotFoundError(FileSystemError):
    """Raised when a required file is not found."""

    def __init__(self, file_path: str):
        super().__init__(
            message=f"File not found: {file_path}",
            error_code="FILE_NOT_FOUND",
            details={"file_path": file_path}
        )


class FileWriteError(FileSystemError):
    """Raised when file cannot be written."""

    def __init__(self, file_path: str, reason: str):
        super().__init__(
            message=f"Failed to write file: {reason}",
            error_code="FILE_WRITE_ERROR",
            details={"file_path": file_path, "reason": reason}
        )
