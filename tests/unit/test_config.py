"""
Unit tests for configuration module.

Tests cover:
- Settings loading and validation
- Nested configuration models
- Field validators
- Helper methods
"""

from pathlib import Path
from unittest.mock import patch

import pytest


class TestProjectSettings:
    """Tests for ProjectSettings model."""

    def test_default_values(self):
        """Test default project settings."""
        from api.config import ProjectSettings

        settings = ProjectSettings()

        assert settings.default_country == "Paraguay"
        assert settings.default_language == "es"
        assert settings.default_type == "digital"
        assert settings.default_year == 2025
        assert settings.num_ideas == 25
        assert settings.ideas_per_batch == 5

    def test_custom_values(self):
        """Test custom project settings."""
        from api.config import ProjectSettings

        settings = ProjectSettings(
            default_country="Argentina",
            default_language="en",
            num_ideas=50,
        )

        assert settings.default_country == "Argentina"
        assert settings.default_language == "en"
        assert settings.num_ideas == 50


class TestScoringSettings:
    """Tests for ScoringSettings model."""

    def test_default_thresholds(self):
        """Test default scoring thresholds."""
        from api.config import ScoringSettings, ScoringThresholds

        settings = ScoringSettings()

        assert settings.thresholds.very_high == 90
        assert settings.thresholds.high == 80
        assert settings.thresholds.medium == 70
        assert settings.thresholds.needs_work == 60

    def test_custom_thresholds(self):
        """Test custom scoring thresholds."""
        from api.config import ScoringSettings, ScoringThresholds

        thresholds = ScoringThresholds(very_high=95, high=85)
        settings = ScoringSettings(thresholds=thresholds)

        assert settings.thresholds.very_high == 95
        assert settings.thresholds.high == 85

    def test_scoring_criteria(self):
        """Test scoring criteria list."""
        from api.config import ScoringCriterion, ScoringSettings

        criteria = [
            ScoringCriterion(name="creativity", weight=1.5),
            ScoringCriterion(name="feasibility", weight=1.0),
        ]
        settings = ScoringSettings(criteria=criteria)

        assert len(settings.criteria) == 2
        assert settings.criteria[0].weight == 1.5


class TestAISettings:
    """Tests for AISettings model."""

    def test_default_providers(self):
        """Test default AI provider settings."""
        from api.config import AISettings

        settings = AISettings()

        assert settings.primary == "anthropic"
        assert settings.fallback == "openai"

    def test_provider_config(self):
        """Test AI provider configuration."""
        from api.config import AIProviderSettings, AISettings

        anthropic_config = AIProviderSettings(
            model="claude-3-opus",
            max_tokens=8192,
            temperature=0.5,
        )
        settings = AISettings(anthropic=anthropic_config)

        assert settings.anthropic.model == "claude-3-opus"
        assert settings.anthropic.max_tokens == 8192
        assert settings.anthropic.temperature == 0.5


class TestExportSettings:
    """Tests for ExportSettings model."""

    def test_default_export_settings(self):
        """Test default export settings."""
        from api.config import ExportSettings

        settings = ExportSettings()

        assert settings.pdf is None
        assert settings.pptx is None

    def test_pdf_export_settings(self):
        """Test PDF export settings."""
        from api.config import ExportFormatSettings, ExportSettings

        pdf_config = ExportFormatSettings(
            font_family="Arial",
            font_size=12,
            include_toc=False,
        )
        settings = ExportSettings(pdf=pdf_config)

        assert settings.pdf.font_family == "Arial"
        assert settings.pdf.font_size == 12
        assert settings.pdf.include_toc is False


class TestSettingsValidators:
    """Tests for Settings field validators."""

    def test_validate_projects_dir_creates_directory(self, tmp_path):
        """Test projects directory is created if missing."""
        from api.config import Settings

        new_dir = tmp_path / "new_projects"
        assert not new_dir.exists()

        with patch.dict("os.environ", {"PROJECTS_DIR": str(new_dir)}):
            # Validator should create the directory
            result = Settings.validate_projects_dir(str(new_dir))
            assert result.exists()

    def test_validate_log_level_valid(self):
        """Test valid log levels pass validation."""
        from api.config import Settings

        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in valid_levels:
            result = Settings.validate_log_level(level)
            assert result == level.upper()

    def test_validate_log_level_lowercase(self):
        """Test lowercase log levels are normalized."""
        from api.config import Settings

        result = Settings.validate_log_level("debug")
        assert result == "DEBUG"

    def test_validate_log_level_invalid(self):
        """Test invalid log level raises error."""
        from api.config import Settings

        with pytest.raises(ValueError) as exc_info:
            Settings.validate_log_level("INVALID")

        assert "Invalid log level" in str(exc_info.value)


class TestSettingsHelperMethods:
    """Tests for Settings helper methods."""

    @pytest.fixture
    def settings_with_criteria(self):
        """Create settings with scoring criteria."""
        from api.config import ScoringCriterion, ScoringSettings, ScoringThresholds

        criteria = [
            ScoringCriterion(name="creativity", weight=2.0),
            ScoringCriterion(name="feasibility", weight=1.0),
            ScoringCriterion(name="impact", weight=1.5),
        ]
        thresholds = ScoringThresholds(
            very_high=90,
            high=80,
            medium=70,
            needs_work=60,
        )

        from api.config import Settings
        with patch.object(Settings, "__init__", lambda self: None):
            settings = Settings()
            settings.scoring = ScoringSettings(criteria=criteria, thresholds=thresholds)
            return settings

    def test_get_tier_very_high(self, settings_with_criteria):
        """Test tier classification for very high scores."""
        tier = settings_with_criteria.get_tier_for_score(95)
        assert tier == "very_high"

    def test_get_tier_high(self, settings_with_criteria):
        """Test tier classification for high scores."""
        tier = settings_with_criteria.get_tier_for_score(85)
        assert tier == "high"

    def test_get_tier_medium(self, settings_with_criteria):
        """Test tier classification for medium scores."""
        tier = settings_with_criteria.get_tier_for_score(75)
        assert tier == "medium"

    def test_get_tier_low(self, settings_with_criteria):
        """Test tier classification for low scores."""
        tier = settings_with_criteria.get_tier_for_score(65)
        assert tier == "low"

    def test_get_tier_very_low(self, settings_with_criteria):
        """Test tier classification for very low scores."""
        tier = settings_with_criteria.get_tier_for_score(50)
        assert tier == "very_low"

    def test_calculate_weighted_score(self, settings_with_criteria):
        """Test weighted score calculation."""
        scores = {
            "creativity": 8.0,
            "feasibility": 7.0,
            "impact": 9.0,
        }

        # Expected: (8*2 + 7*1 + 9*1.5) / (2+1+1.5) = (16+7+13.5) / 4.5 = 8.11
        result = settings_with_criteria.calculate_weighted_score(scores)

        assert round(result, 2) == 8.11

    def test_calculate_weighted_score_partial(self, settings_with_criteria):
        """Test weighted score with partial scores."""
        scores = {
            "creativity": 8.0,
            # Missing feasibility and impact
        }

        result = settings_with_criteria.calculate_weighted_score(scores)

        assert result == 8.0  # Only one score, weight 2.0

    def test_calculate_weighted_score_empty(self, settings_with_criteria):
        """Test weighted score with no scores."""
        scores = {}

        result = settings_with_criteria.calculate_weighted_score(scores)

        assert result == 0


class TestSettingsDefaults:
    """Tests for Settings default values."""

    def test_default_database_url(self):
        """Test default database URL."""
        from api.config import Settings

        with patch.object(Settings, "__init__", lambda self: None):
            settings = Settings()
            # Access default through field
            assert "sqlite" in Settings.model_fields["database_url"].default

    def test_default_rate_limit_settings(self):
        """Test default rate limiting settings."""
        from api.config import Settings

        defaults = {
            "rate_limit_enabled": True,
            "rate_limit_requests": 100,
            "rate_limit_window": 60,
        }

        for field_name, expected_value in defaults.items():
            default = Settings.model_fields[field_name].default
            assert default == expected_value

    def test_default_linkedin_settings(self):
        """Test default LinkedIn settings."""
        from api.config import Settings

        assert Settings.model_fields["linkedin_daily_limit"].default == 20
        assert Settings.model_fields["linkedin_headless"].default is True


class TestSettingsSingleton:
    """Tests for settings singleton."""

    def test_get_settings_returns_cached(self):
        """Test get_settings returns cached instance."""
        from api.config import get_settings

        # Clear cache first
        get_settings.cache_clear()

        settings1 = get_settings()
        settings2 = get_settings()

        # Should be same instance (cached)
        assert settings1 is settings2

    def test_get_project_config_alias(self):
        """Test deprecated get_project_config returns same settings."""
        from api.config import get_project_config, get_settings

        # Clear cache
        get_settings.cache_clear()

        settings = get_settings()
        project_config = get_project_config()

        assert settings is project_config


class TestResearchSettings:
    """Tests for ResearchSettings model."""

    def test_default_categories(self):
        """Test default research categories."""
        from api.config import ResearchSettings

        settings = ResearchSettings()

        assert settings.categories == []

    def test_custom_categories(self):
        """Test custom research categories."""
        from api.config import ResearchCategory, ResearchSettings

        categories = [
            ResearchCategory(
                id="market",
                name="Market Research",
                files=["market-analysis.md", "competitors.md"],
            ),
            ResearchCategory(
                id="consumer",
                name="Consumer Insights",
                files=["personas.md"],
            ),
        ]
        settings = ResearchSettings(categories=categories)

        assert len(settings.categories) == 2
        assert settings.categories[0].id == "market"
        assert len(settings.categories[0].files) == 2
