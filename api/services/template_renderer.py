"""
Template Rendering Service

Renders Jinja2 templates for generating markdown files.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateError, TemplateNotFound

from ..exceptions import TemplateRenderError
from ..logging_config import get_logger

logger = get_logger("template_renderer")


# =============================================================================
# Template Renderer
# =============================================================================

class TemplateRenderer:
    """
    Renders Jinja2 templates for campaign documents.
    """

    def __init__(self, templates_dir: Path | None = None):
        """
        Initialize template renderer.

        Args:
            templates_dir: Path to templates directory
        """
        if templates_dir is None:
            templates_dir = Path(__file__).parent.parent.parent / "config" / "templates"

        self.templates_dir = templates_dir
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,  # Markdown output
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Add custom filters
        self._env.filters["format_date"] = self._format_date
        self._env.filters["format_number"] = self._format_number
        self._env.filters["tier_emoji"] = self._tier_emoji
        self._env.filters["score_color"] = self._score_color

        logger.info(f"Initialized template renderer from: {templates_dir}")

    # =========================================================================
    # Custom Filters
    # =========================================================================

    @staticmethod
    def _format_date(value: datetime | str, format: str = "%d/%m/%Y") -> str:
        """Format a date value."""
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.strftime(format)

    @staticmethod
    def _format_number(value: float, decimals: int = 1) -> str:
        """Format a number with specified decimal places."""
        return f"{value:.{decimals}f}"

    @staticmethod
    def _tier_emoji(tier: str) -> str:
        """Get emoji for tier classification."""
        emojis = {
            "very_high": "🏆",
            "high": "⭐",
            "medium": "✅",
            "low": "📋",
            "very_low": "📝"
        }
        return emojis.get(tier, "")

    @staticmethod
    def _score_color(score: float) -> str:
        """Get color indicator for score (for markdown)."""
        if score >= 9:
            return "🟢"
        elif score >= 7:
            return "🟡"
        elif score >= 5:
            return "🟠"
        else:
            return "🔴"

    # =========================================================================
    # Rendering Methods
    # =========================================================================

    def render(self, template_name: str, **context: Any) -> str:
        """
        Render a template with context.

        Args:
            template_name: Template filename (e.g., "idea.md.j2")
            **context: Variables to pass to template

        Returns:
            Rendered template content
        """
        try:
            template = self._env.get_template(template_name)

            # Add common context
            context["generated_at"] = datetime.utcnow()
            context["generator_version"] = "1.0.0"

            rendered = template.render(**context)
            logger.debug(f"Rendered template '{template_name}': {len(rendered)} chars")

            return rendered

        except TemplateNotFound:
            logger.error(f"Template not found: {template_name}")
            raise TemplateRenderError(template_name, "Template not found")

        except TemplateError as e:
            logger.error(f"Template error in '{template_name}': {e}")
            raise TemplateRenderError(template_name, str(e))

    def render_idea(
        self,
        idea_number: int,
        title: str,
        concept: str,
        insight: str,
        execution: dict[str, str],
        scores: dict[str, float],
        overall_score: float,
        tier: str,
        strengths: list[str],
        weaknesses: list[str],
        recommendation: str
    ) -> str:
        """
        Render an idea document.

        Args:
            idea_number: Idea sequential number
            title: Idea title
            concept: Core concept description
            insight: Consumer insight
            execution: Dict of format to execution description
            scores: Dict of criterion name to score
            overall_score: Weighted overall score
            tier: Tier classification
            strengths: List of strengths
            weaknesses: List of weaknesses
            recommendation: Final recommendation

        Returns:
            Rendered markdown
        """
        return self.render(
            "idea.md.j2",
            idea_number=idea_number,
            title=title,
            concept=concept,
            insight=insight,
            execution=execution,
            scores=scores,
            overall_score=overall_score,
            tier=tier,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendation=recommendation
        )

    def render_quick_reference(
        self,
        project_name: str,
        challenge: str,
        market_snapshot: dict[str, str],
        target: dict[str, str],
        insights: list[dict[str, str]],
        dos: list[str],
        donts: list[str],
        brainstorm_questions: list[str]
    ) -> str:
        """
        Render quick reference document.

        Args:
            project_name: Project name
            challenge: One-liner challenge
            market_snapshot: Market data dict
            target: Target audience dict
            insights: List of insight dicts
            dos: List of do's
            donts: List of don'ts
            brainstorm_questions: List of questions

        Returns:
            Rendered markdown
        """
        return self.render(
            "quick_reference.md.j2",
            project_name=project_name,
            challenge=challenge,
            market_snapshot=market_snapshot,
            target=target,
            insights=insights,
            dos=dos,
            donts=donts,
            brainstorm_questions=brainstorm_questions
        )

    def render_brief(
        self,
        client: str,
        product: str,
        objective: str,
        target: dict[str, Any],
        problem: str,
        mandatories: list[str],
        budget: str,
        timing: dict[str, str],
        formats: list[str],
        kpis: list[str],
        context: str
    ) -> str:
        """
        Render expanded brief document.

        Args:
            client: Client name
            product: Product name
            objective: Communication objective
            target: Target audience info
            problem: Problem to solve
            mandatories: Brand mandatories
            budget: Budget amount
            timing: Timeline dict
            formats: Required formats
            kpis: KPIs list
            context: Additional context

        Returns:
            Rendered markdown
        """
        return self.render(
            "brief.md.j2",
            client=client,
            product=product,
            objective=objective,
            target=target,
            problem=problem,
            mandatories=mandatories,
            budget=budget,
            timing=timing,
            formats=formats,
            kpis=kpis,
            context=context
        )

    def render_research_file(
        self,
        title: str,
        category: str,
        content: str,
        sources: list[dict[str, str]],
        key_statistics: list[str] | None = None
    ) -> str:
        """
        Render a research file.

        Args:
            title: Document title
            category: Research category
            content: Main content
            sources: List of source dicts
            key_statistics: Optional list of key stats

        Returns:
            Rendered markdown
        """
        return self.render(
            "research_file.md.j2",
            title=title,
            category=category,
            content=content,
            sources=sources,
            key_statistics=key_statistics or []
        )

    def render_ideas_summary(
        self,
        project_name: str,
        total_ideas: int,
        ideas: list[dict[str, Any]],
        top_ideas: list[dict[str, Any]],
        tier_distribution: dict[str, int],
        recommendations: list[str]
    ) -> str:
        """
        Render ideas summary document.

        Args:
            project_name: Project name
            total_ideas: Total number of ideas
            ideas: All ideas with basic info
            top_ideas: Top ranked ideas
            tier_distribution: Count per tier
            recommendations: Final recommendations

        Returns:
            Rendered markdown
        """
        return self.render(
            "ideas_summary.md.j2",
            project_name=project_name,
            total_ideas=total_ideas,
            ideas=ideas,
            top_ideas=top_ideas,
            tier_distribution=tier_distribution,
            recommendations=recommendations
        )


# =============================================================================
# Singleton Access
# =============================================================================

_renderer: TemplateRenderer | None = None


def get_template_renderer() -> TemplateRenderer:
    """Get singleton template renderer."""
    global _renderer
    if _renderer is None:
        _renderer = TemplateRenderer()
    return _renderer
