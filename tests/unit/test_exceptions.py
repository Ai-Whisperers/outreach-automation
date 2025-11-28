"""
Unit tests for custom exception classes.

Tests cover:
- Base exception behavior
- All exception subclasses
- Error code assignment
- Details dictionary handling
- to_dict() conversion
"""

import pytest


class TestCampaignGeneratorError:
    """Tests for base CampaignGeneratorError."""

    def test_basic_creation(self):
        """Test basic exception creation."""
        from api.exceptions import CampaignGeneratorError

        error = CampaignGeneratorError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.error_code == "UNKNOWN_ERROR"
        assert error.details == {}

    def test_with_error_code(self):
        """Test exception with custom error code."""
        from api.exceptions import CampaignGeneratorError

        error = CampaignGeneratorError(
            message="Custom error",
            error_code="CUSTOM_ERROR",
        )

        assert error.error_code == "CUSTOM_ERROR"

    def test_with_details(self):
        """Test exception with details dict."""
        from api.exceptions import CampaignGeneratorError

        error = CampaignGeneratorError(
            message="Error with context",
            details={"key": "value", "count": 42},
        )

        assert error.details["key"] == "value"
        assert error.details["count"] == 42

    def test_to_dict(self):
        """Test conversion to dictionary."""
        from api.exceptions import CampaignGeneratorError

        error = CampaignGeneratorError(
            message="Test error",
            error_code="TEST_ERROR",
            details={"field": "username"},
        )

        result = error.to_dict()

        assert result["error"] == "TEST_ERROR"
        assert result["message"] == "Test error"
        assert result["details"]["field"] == "username"


class TestConfigurationErrors:
    """Tests for configuration-related exceptions."""

    def test_configuration_error(self):
        """Test ConfigurationError."""
        from api.exceptions import ConfigurationError

        error = ConfigurationError("Invalid config")

        assert error.error_code == "CONFIGURATION_ERROR"
        assert "Invalid config" in error.message

    def test_configuration_error_with_details(self):
        """Test ConfigurationError with details."""
        from api.exceptions import ConfigurationError

        error = ConfigurationError(
            "Missing required field",
            details={"field": "api_key"},
        )

        assert error.details["field"] == "api_key"

    def test_missing_api_key_error(self):
        """Test MissingAPIKeyError."""
        from api.exceptions import MissingAPIKeyError

        error = MissingAPIKeyError("anthropic")

        assert error.details["provider"] == "anthropic"
        assert "anthropic" in error.message
        assert "not configured" in error.message.lower()


class TestAIProviderErrors:
    """Tests for AI provider-related exceptions."""

    def test_ai_provider_error(self):
        """Test AIProviderError."""
        from api.exceptions import AIProviderError

        error = AIProviderError(
            message="API call failed",
            provider="openai",
        )

        assert error.error_code == "AI_PROVIDER_ERROR"
        assert error.details["provider"] == "openai"

    def test_ai_provider_error_custom_code(self):
        """Test AIProviderError with custom error code."""
        from api.exceptions import AIProviderError

        error = AIProviderError(
            message="Specific error",
            provider="anthropic",
            error_code="ANTHROPIC_SPECIFIC",
        )

        assert error.error_code == "ANTHROPIC_SPECIFIC"

    def test_ai_rate_limit_error(self):
        """Test AIRateLimitError."""
        from api.exceptions import AIRateLimitError

        error = AIRateLimitError("openai", retry_after=60)

        assert error.error_code == "AI_RATE_LIMIT"
        assert error.details["provider"] == "openai"
        assert error.details["retry_after_seconds"] == 60
        assert "Rate limit" in error.message

    def test_ai_rate_limit_error_no_retry(self):
        """Test AIRateLimitError without retry_after."""
        from api.exceptions import AIRateLimitError

        error = AIRateLimitError("gemini")

        assert "retry_after_seconds" not in error.details

    def test_ai_response_error(self):
        """Test AIResponseError."""
        from api.exceptions import AIResponseError

        error = AIResponseError("anthropic", "Invalid JSON format")

        assert error.error_code == "AI_RESPONSE_ERROR"
        assert error.details["reason"] == "Invalid JSON format"
        assert "Invalid response" in error.message

    def test_ai_timeout_error(self):
        """Test AITimeoutError."""
        from api.exceptions import AITimeoutError

        error = AITimeoutError("openai", timeout_seconds=30)

        assert error.error_code == "AI_TIMEOUT"
        assert error.details["timeout_seconds"] == 30
        assert "timed out" in error.message
        assert "30s" in error.message


class TestProjectErrors:
    """Tests for project-related exceptions."""

    def test_project_not_found_error(self):
        """Test ProjectNotFoundError."""
        from api.exceptions import ProjectNotFoundError

        error = ProjectNotFoundError("my-project-123")

        assert error.error_code == "PROJECT_NOT_FOUND"
        assert error.details["project_id"] == "my-project-123"
        assert "my-project-123" in error.message

    def test_project_exists_error(self):
        """Test ProjectExistsError."""
        from api.exceptions import ProjectExistsError

        error = ProjectExistsError("existing-project")

        assert error.error_code == "PROJECT_EXISTS"
        assert "already exists" in error.message.lower()

    def test_project_validation_error(self):
        """Test ProjectValidationError."""
        from api.exceptions import ProjectValidationError

        validation_errors = [
            {"field": "name", "error": "required"},
            {"field": "country", "error": "invalid"},
        ]
        error = ProjectValidationError(
            "Validation failed",
            validation_errors=validation_errors,
        )

        assert error.error_code == "PROJECT_VALIDATION_ERROR"
        assert len(error.details["validation_errors"]) == 2


class TestBriefErrors:
    """Tests for brief-related exceptions."""

    def test_brief_parsing_error(self):
        """Test BriefParsingError."""
        from api.exceptions import BriefParsingError

        error = BriefParsingError("Invalid markdown format")

        assert error.error_code == "BRIEF_PARSING_ERROR"
        assert error.details["reason"] == "Invalid markdown format"

    def test_incomplete_brief_error(self):
        """Test IncompleteBriefError."""
        from api.exceptions import IncompleteBriefError

        error = IncompleteBriefError(["brand_name", "target_audience"])

        assert error.error_code == "INCOMPLETE_BRIEF"
        assert error.details["missing_fields"] == ["brand_name", "target_audience"]
        assert "brand_name" in error.message


class TestResearchErrors:
    """Tests for research-related exceptions."""

    def test_source_fetch_error(self):
        """Test SourceFetchError."""
        from api.exceptions import SourceFetchError

        error = SourceFetchError(
            "https://example.com/article",
            "Connection timeout",
        )

        assert error.error_code == "SOURCE_FETCH_ERROR"
        assert error.details["url"] == "https://example.com/article"
        assert error.details["reason"] == "Connection timeout"

    def test_content_extraction_error(self):
        """Test ContentExtractionError."""
        from api.exceptions import ContentExtractionError

        error = ContentExtractionError(
            "https://example.com/pdf",
            "PDF parsing failed",
        )

        assert error.error_code == "CONTENT_EXTRACTION_ERROR"
        assert "extract content" in error.message.lower()


class TestIdeaGenerationErrors:
    """Tests for idea generation-related exceptions."""

    def test_insufficient_data_error(self):
        """Test InsufficientDataError."""
        from api.exceptions import InsufficientDataError

        error = InsufficientDataError("No research files found")

        assert error.error_code == "INSUFFICIENT_DATA"
        assert error.details["reason"] == "No research files found"

    def test_scoring_error(self):
        """Test ScoringError."""
        from api.exceptions import ScoringError

        error = ScoringError("idea-001", "Invalid score format")

        assert error.error_code == "SCORING_ERROR"
        assert error.details["idea_id"] == "idea-001"
        assert error.details["reason"] == "Invalid score format"


class TestExportErrors:
    """Tests for export-related exceptions."""

    def test_pdf_generation_error(self):
        """Test PDFGenerationError."""
        from api.exceptions import PDFGenerationError

        error = PDFGenerationError("Font not found")

        assert error.error_code == "PDF_GENERATION_ERROR"
        assert error.details["reason"] == "Font not found"

    def test_powerpoint_generation_error(self):
        """Test PowerPointGenerationError."""
        from api.exceptions import PowerPointGenerationError

        error = PowerPointGenerationError("Template invalid")

        assert error.error_code == "PPTX_GENERATION_ERROR"
        assert "PowerPoint" in error.message

    def test_template_render_error(self):
        """Test TemplateRenderError."""
        from api.exceptions import TemplateRenderError

        error = TemplateRenderError("idea-template", "Missing variable: title")

        assert error.error_code == "TEMPLATE_RENDER_ERROR"
        assert error.details["template"] == "idea-template"
        assert "render" in error.message.lower()


class TestFileSystemErrors:
    """Tests for file system-related exceptions."""

    def test_file_not_found_error(self):
        """Test FileNotFoundError."""
        from api.exceptions import FileNotFoundError

        error = FileNotFoundError("/path/to/missing/file.md")

        assert error.error_code == "FILE_NOT_FOUND"
        assert error.details["file_path"] == "/path/to/missing/file.md"

    def test_file_write_error(self):
        """Test FileWriteError."""
        from api.exceptions import FileWriteError

        error = FileWriteError("/path/to/file.md", "Permission denied")

        assert error.error_code == "FILE_WRITE_ERROR"
        assert error.details["file_path"] == "/path/to/file.md"
        assert error.details["reason"] == "Permission denied"


class TestExceptionInheritance:
    """Tests for exception inheritance hierarchy."""

    def test_config_error_inheritance(self):
        """Test ConfigurationError inherits from base."""
        from api.exceptions import CampaignGeneratorError, ConfigurationError

        error = ConfigurationError("test")
        assert isinstance(error, CampaignGeneratorError)

    def test_ai_error_inheritance(self):
        """Test AI errors inherit from AIProviderError."""
        from api.exceptions import (
            AIProviderError,
            AIRateLimitError,
            AIResponseError,
            AITimeoutError,
        )

        assert issubclass(AIRateLimitError, AIProviderError)
        assert issubclass(AIResponseError, AIProviderError)
        assert issubclass(AITimeoutError, AIProviderError)

    def test_project_error_inheritance(self):
        """Test project errors inherit from ProjectError."""
        from api.exceptions import (
            ProjectError,
            ProjectExistsError,
            ProjectNotFoundError,
            ProjectValidationError,
        )

        assert issubclass(ProjectNotFoundError, ProjectError)
        assert issubclass(ProjectExistsError, ProjectError)
        assert issubclass(ProjectValidationError, ProjectError)

    def test_export_error_inheritance(self):
        """Test export errors inherit from ExportError."""
        from api.exceptions import (
            ExportError,
            PDFGenerationError,
            PowerPointGenerationError,
            TemplateRenderError,
        )

        assert issubclass(PDFGenerationError, ExportError)
        assert issubclass(PowerPointGenerationError, ExportError)
        assert issubclass(TemplateRenderError, ExportError)

    def test_all_inherit_from_base(self):
        """Test all exceptions inherit from CampaignGeneratorError."""
        from api.exceptions import (
            BriefError,
            CampaignGeneratorError,
            ConfigurationError,
            ExportError,
            FileSystemError,
            IdeaGenerationError,
            ProjectError,
            ResearchError,
        )

        all_errors = [
            BriefError,
            ConfigurationError,
            ExportError,
            FileSystemError,
            IdeaGenerationError,
            ProjectError,
            ResearchError,
        ]

        for error_class in all_errors:
            assert issubclass(error_class, CampaignGeneratorError)
