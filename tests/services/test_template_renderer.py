"""
Tests for TemplateRenderer.

Tests cover:
- Template initialization
- Custom filters
- Template rendering
- Specialized renderers (idea, brief, research, etc.)
- Error handling
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestTemplateRendererInit:
    """Tests for TemplateRenderer initialization."""

    def test_template_renderer_initialization(self, tmp_path):
        """Test TemplateRenderer initializes correctly."""
        from api.services.template_renderer import TemplateRenderer

        renderer = TemplateRenderer(templates_dir=tmp_path)

        assert renderer.templates_dir == tmp_path
        assert renderer._env is not None

    def test_template_renderer_default_path(self):
        """Test TemplateRenderer uses default path."""
        with patch("pathlib.Path.exists", return_value=True):
            from api.services.template_renderer import TemplateRenderer

            renderer = TemplateRenderer()

            assert renderer.templates_dir is not None

    def test_template_renderer_custom_filters_registered(self, tmp_path):
        """Test custom filters are registered."""
        from api.services.template_renderer import TemplateRenderer

        renderer = TemplateRenderer(templates_dir=tmp_path)

        assert "format_date" in renderer._env.filters
        assert "format_number" in renderer._env.filters
        assert "tier_emoji" in renderer._env.filters
        assert "score_color" in renderer._env.filters


class TestCustomFilters:
    """Tests for custom Jinja2 filters."""

    def test_format_date_from_datetime(self):
        """Test format_date with datetime object."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._format_date(datetime(2024, 1, 15))

        assert result == "15/01/2024"

    def test_format_date_from_string(self):
        """Test format_date with ISO string."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._format_date("2024-01-15T10:30:00")

        assert result == "15/01/2024"

    def test_format_date_custom_format(self):
        """Test format_date with custom format."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._format_date(datetime(2024, 1, 15), "%Y-%m-%d")

        assert result == "2024-01-15"

    def test_format_number_default(self):
        """Test format_number with default decimals."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._format_number(8.567)

        assert result == "8.6"

    def test_format_number_custom_decimals(self):
        """Test format_number with custom decimals."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._format_number(8.567, decimals=2)

        assert result == "8.57"

    def test_tier_emoji_very_high(self):
        """Test tier_emoji for very_high tier."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._tier_emoji("very_high")

        assert result == "🏆"

    def test_tier_emoji_high(self):
        """Test tier_emoji for high tier."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._tier_emoji("high")

        assert result == "⭐"

    def test_tier_emoji_medium(self):
        """Test tier_emoji for medium tier."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._tier_emoji("medium")

        assert result == "✅"

    def test_tier_emoji_low(self):
        """Test tier_emoji for low tier."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._tier_emoji("low")

        assert result == "📋"

    def test_tier_emoji_very_low(self):
        """Test tier_emoji for very_low tier."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._tier_emoji("very_low")

        assert result == "📝"

    def test_tier_emoji_unknown(self):
        """Test tier_emoji for unknown tier."""
        from api.services.template_renderer import TemplateRenderer

        result = TemplateRenderer._tier_emoji("unknown")

        assert result == ""

    def test_score_color_high(self):
        """Test score_color for high scores."""
        from api.services.template_renderer import TemplateRenderer

        assert TemplateRenderer._score_color(9.5) == "🟢"
        assert TemplateRenderer._score_color(9.0) == "🟢"

    def test_score_color_medium_high(self):
        """Test score_color for medium-high scores."""
        from api.services.template_renderer import TemplateRenderer

        assert TemplateRenderer._score_color(8.0) == "🟡"
        assert TemplateRenderer._score_color(7.0) == "🟡"

    def test_score_color_medium_low(self):
        """Test score_color for medium-low scores."""
        from api.services.template_renderer import TemplateRenderer

        assert TemplateRenderer._score_color(6.0) == "🟠"
        assert TemplateRenderer._score_color(5.0) == "🟠"

    def test_score_color_low(self):
        """Test score_color for low scores."""
        from api.services.template_renderer import TemplateRenderer

        assert TemplateRenderer._score_color(4.0) == "🔴"
        assert TemplateRenderer._score_color(2.0) == "🔴"


class TestRenderMethod:
    """Tests for the render method."""

    @pytest.fixture
    def renderer_with_template(self, tmp_path):
        """Create renderer with a test template."""
        # Create test template
        template_content = """
# {{ title }}

Generated at: {{ generated_at|format_date }}

Content: {{ content }}
        """
        (tmp_path / "test.md.j2").write_text(template_content)

        from api.services.template_renderer import TemplateRenderer

        return TemplateRenderer(templates_dir=tmp_path)

    def test_render_basic_template(self, renderer_with_template):
        """Test rendering basic template."""
        result = renderer_with_template.render(
            "test.md.j2",
            title="Test Title",
            content="Some content here"
        )

        assert "Test Title" in result
        assert "Some content here" in result

    def test_render_adds_common_context(self, renderer_with_template):
        """Test render adds generated_at and version."""
        result = renderer_with_template.render(
            "test.md.j2",
            title="Test",
            content="Content"
        )

        # generated_at should be formatted
        assert "/" in result  # Date format includes slashes

    def test_render_template_not_found(self, tmp_path):
        """Test render raises error for missing template."""
        from api.services.template_renderer import TemplateRenderer
        from api.exceptions import TemplateRenderError

        renderer = TemplateRenderer(templates_dir=tmp_path)

        with pytest.raises(TemplateRenderError) as exc_info:
            renderer.render("nonexistent.md.j2", title="Test")

        assert "not found" in str(exc_info.value).lower()

    def test_render_template_error(self, tmp_path):
        """Test render handles template syntax errors."""
        # Create template with invalid syntax
        (tmp_path / "bad.md.j2").write_text("{{ invalid syntax }")

        from api.services.template_renderer import TemplateRenderer
        from api.exceptions import TemplateRenderError

        renderer = TemplateRenderer(templates_dir=tmp_path)

        with pytest.raises(TemplateRenderError):
            renderer.render("bad.md.j2")


class TestRenderIdea:
    """Tests for render_idea method."""

    @pytest.fixture
    def renderer_with_idea_template(self, tmp_path):
        """Create renderer with idea template."""
        template_content = """
# {{ idea_number }}. {{ title }}

## Concepto
{{ concept }}

## Insight
{{ insight }}

## Score: {{ overall_score|format_number }} {{ tier|tier_emoji }}

## Scores
{% for criterion, score in scores.items() %}
- {{ criterion }}: {{ score }}
{% endfor %}

## Strengths
{% for strength in strengths %}
- {{ strength }}
{% endfor %}

## Weaknesses
{% for weakness in weaknesses %}
- {{ weakness }}
{% endfor %}

## Recommendation
{{ recommendation }}
        """
        (tmp_path / "idea.md.j2").write_text(template_content)

        from api.services.template_renderer import TemplateRenderer

        return TemplateRenderer(templates_dir=tmp_path)

    def test_render_idea_full(self, renderer_with_idea_template):
        """Test rendering full idea document."""
        result = renderer_with_idea_template.render_idea(
            idea_number=1,
            title="Great Campaign Idea",
            concept="A concept description",
            insight="Consumer insight here",
            execution={"digital": "Digital execution", "social": "Social execution"},
            scores={"originality": 8.5, "relevance": 9.0},
            overall_score=8.75,
            tier="high",
            strengths=["Strong emotional appeal", "Fresh approach"],
            weaknesses=["Budget intensive"],
            recommendation="Recommend for development"
        )

        assert "Great Campaign Idea" in result
        assert "8.8" in result  # Formatted score
        assert "⭐" in result  # Tier emoji
        assert "Strong emotional appeal" in result
        assert "Budget intensive" in result


class TestRenderQuickReference:
    """Tests for render_quick_reference method."""

    @pytest.fixture
    def renderer_with_qr_template(self, tmp_path):
        """Create renderer with quick reference template."""
        template_content = """
# Quick Reference: {{ project_name }}

## Challenge
{{ challenge }}

## Market Snapshot
{% for key, value in market_snapshot.items() %}
- {{ key }}: {{ value }}
{% endfor %}

## Target Audience
{% for key, value in target.items() %}
- {{ key }}: {{ value }}
{% endfor %}

## Do's
{% for item in dos %}
- {{ item }}
{% endfor %}

## Don'ts
{% for item in donts %}
- {{ item }}
{% endfor %}
        """
        (tmp_path / "quick_reference.md.j2").write_text(template_content)

        from api.services.template_renderer import TemplateRenderer

        return TemplateRenderer(templates_dir=tmp_path)

    def test_render_quick_reference(self, renderer_with_qr_template):
        """Test rendering quick reference document."""
        result = renderer_with_qr_template.render_quick_reference(
            project_name="Campaign 2024",
            challenge="Increase brand awareness",
            market_snapshot={"size": "$1B", "growth": "15%"},
            target={"age": "25-35", "interests": "Technology"},
            insights=[{"insight": "Key insight", "implication": "Action"}],
            dos=["Be authentic", "Use local references"],
            donts=["Be generic", "Ignore cultural context"],
            brainstorm_questions=["What would surprise them?"]
        )

        assert "Campaign 2024" in result
        assert "Increase brand awareness" in result
        assert "Be authentic" in result
        assert "Be generic" in result


class TestRenderBrief:
    """Tests for render_brief method."""

    @pytest.fixture
    def renderer_with_brief_template(self, tmp_path):
        """Create renderer with brief template."""
        template_content = """
# Brief: {{ client }} - {{ product }}

## Objective
{{ objective }}

## Target
{% for key, value in target.items() %}
- {{ key }}: {{ value }}
{% endfor %}

## Problem
{{ problem }}

## Budget
{{ budget }}

## Formats
{% for format in formats %}
- {{ format }}
{% endfor %}
        """
        (tmp_path / "brief.md.j2").write_text(template_content)

        from api.services.template_renderer import TemplateRenderer

        return TemplateRenderer(templates_dir=tmp_path)

    def test_render_brief(self, renderer_with_brief_template):
        """Test rendering brief document."""
        result = renderer_with_brief_template.render_brief(
            client="Acme Corp",
            product="Product X",
            objective="Launch awareness campaign",
            target={"age": "25-45", "income": "Middle"},
            problem="Low brand recognition",
            mandatories=["Logo visible", "Tagline included"],
            budget="$100,000",
            timing={"start": "2024-02", "end": "2024-04"},
            formats=["TV", "Digital", "Social"],
            kpis=["Reach 1M", "Engagement 5%"],
            context="Competitive market"
        )

        assert "Acme Corp" in result
        assert "Product X" in result
        assert "$100,000" in result
        assert "Digital" in result


class TestRenderResearchFile:
    """Tests for render_research_file method."""

    @pytest.fixture
    def renderer_with_research_template(self, tmp_path):
        """Create renderer with research file template."""
        template_content = """
# {{ title }}

Category: {{ category }}

{{ content }}

## Sources
{% for source in sources %}
- [{{ source.title }}]({{ source.url }})
{% endfor %}

{% if key_statistics %}
## Key Statistics
{% for stat in key_statistics %}
- {{ stat }}
{% endfor %}
{% endif %}
        """
        (tmp_path / "research_file.md.j2").write_text(template_content)

        from api.services.template_renderer import TemplateRenderer

        return TemplateRenderer(templates_dir=tmp_path)

    def test_render_research_file(self, renderer_with_research_template):
        """Test rendering research file."""
        result = renderer_with_research_template.render_research_file(
            title="Market Analysis 2024",
            category="market-research",
            content="The market is growing rapidly...",
            sources=[
                {"title": "Source 1", "url": "https://source1.com"},
                {"title": "Source 2", "url": "https://source2.com"},
            ],
            key_statistics=["15% growth", "$1B market size"]
        )

        assert "Market Analysis 2024" in result
        assert "market-research" in result
        assert "Source 1" in result
        assert "15% growth" in result

    def test_render_research_file_no_stats(self, renderer_with_research_template):
        """Test rendering research file without statistics."""
        result = renderer_with_research_template.render_research_file(
            title="Basic Research",
            category="general",
            content="Research content",
            sources=[],
            key_statistics=None
        )

        assert "Basic Research" in result


class TestRenderIdeasSummary:
    """Tests for render_ideas_summary method."""

    @pytest.fixture
    def renderer_with_summary_template(self, tmp_path):
        """Create renderer with ideas summary template."""
        template_content = """
# Ideas Summary: {{ project_name }}

Total Ideas: {{ total_ideas }}

## Top Ideas
{% for idea in top_ideas %}
{{ loop.index }}. {{ idea.title }} ({{ idea.score }})
{% endfor %}

## Tier Distribution
{% for tier, count in tier_distribution.items() %}
- {{ tier }}: {{ count }}
{% endfor %}

## Recommendations
{% for rec in recommendations %}
- {{ rec }}
{% endfor %}
        """
        (tmp_path / "ideas_summary.md.j2").write_text(template_content)

        from api.services.template_renderer import TemplateRenderer

        return TemplateRenderer(templates_dir=tmp_path)

    def test_render_ideas_summary(self, renderer_with_summary_template):
        """Test rendering ideas summary."""
        result = renderer_with_summary_template.render_ideas_summary(
            project_name="Campaign 2024",
            total_ideas=25,
            ideas=[{"title": "Idea 1", "score": 8.5}],
            top_ideas=[
                {"title": "Top Idea 1", "score": 9.5},
                {"title": "Top Idea 2", "score": 9.0},
            ],
            tier_distribution={"very_high": 2, "high": 5, "medium": 10},
            recommendations=["Focus on top 3", "Develop visual concepts"]
        )

        assert "Campaign 2024" in result
        assert "25" in result
        assert "Top Idea 1" in result
        assert "very_high" in result
        assert "Focus on top 3" in result


class TestSingleton:
    """Tests for singleton access."""

    def test_get_template_renderer_singleton(self):
        """Test get_template_renderer returns singleton."""
        import api.services.template_renderer as module
        module._renderer = None

        with patch.object(Path, "exists", return_value=True):
            from api.services.template_renderer import get_template_renderer

            renderer1 = get_template_renderer()
            renderer2 = get_template_renderer()

            assert renderer1 is renderer2
