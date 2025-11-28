"""
Iteration Service

Provides AI-driven analysis for iterative research and idea improvement loops.
"""

import json

from ..config import get_settings
from ..exceptions import CampaignGeneratorError
from ..logging_config import get_logger
from .ai_client import get_ai_manager
from .file_operations import get_file_service

logger = get_logger("iteration_service")


class IterationError(CampaignGeneratorError):
    """Raised when iteration analysis fails."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=message,
            error_code="ITERATION_ERROR",
            details=details or {}
        )


class IterationService:
    """
    Service for analyzing gaps and generating targeted improvements.
    """

    # Research categories with descriptions
    RESEARCH_CATEGORIES = {
        "01-mercado-general": "General market analysis, size, growth, trends",
        "02-competencia": "Competitor analysis, positioning, strategies",
        "03-consumidor": "Consumer insights, behaviors, motivations",
        "04-marca": "Brand analysis, equity, perception",
        "05-tendencias": "Market and cultural trends",
        "06-medios": "Media consumption, channels, touchpoints",
        "07-cultural": "Cultural context, local insights",
        "08-digital": "Digital ecosystem, platforms, behaviors",
        "09-referencias": "Creative references, case studies",
        "10-investigacion-creativa": "Additional creative research"
    }

    def __init__(self):
        self.settings = get_settings()
        self.ai_manager = get_ai_manager()
        self.file_ops = get_file_service()

    async def analyze_research_gaps(self, project_id: str) -> dict:
        """
        Analyze research coverage and identify gaps.

        Returns:
            Dict with coverage score, gaps, and suggested queries
        """
        try:
            project_dir = self.file_ops.get_project_path(project_id)

            # Load brief for context
            brief_path = project_dir / "brief-expanded.md"
            brief_content = ""
            if brief_path.exists():
                brief_content = brief_path.read_text(encoding="utf-8")

            # Check research coverage by category
            research_dir = project_dir / "research"
            category_coverage = {}
            total_sources = 0

            for category, description in self.RESEARCH_CATEGORIES.items():
                category_dir = research_dir / category
                if category_dir.exists():
                    files = list(category_dir.glob("*.md"))
                    category_coverage[category] = {
                        "count": len(files),
                        "description": description,
                        "files": [f.name for f in files]
                    }
                    total_sources += len(files)
                else:
                    category_coverage[category] = {
                        "count": 0,
                        "description": description,
                        "files": []
                    }

            # Load quick reference if exists
            quick_ref_path = project_dir / "quick-reference.md"
            quick_ref_content = ""
            if quick_ref_path.exists():
                quick_ref_content = quick_ref_path.read_text(encoding="utf-8")

            # AI analysis prompt
            prompt = f"""Analyze the research coverage for this campaign project and identify gaps.

## Brief Summary
{brief_content[:3000] if brief_content else "No brief available"}

## Current Research Coverage
{json.dumps(category_coverage, indent=2)}

## Quick Reference (if available)
{quick_ref_content[:2000] if quick_ref_content else "Not yet generated"}

## Task
Analyze the research coverage and provide:

1. **Coverage Score** (0-100): How well does the current research cover what's needed for this campaign?

2. **Gaps**: List specific gaps in research, organized by category. For each gap:
   - Which category needs more research
   - What specific information is missing
   - Why it's important for this campaign

3. **Suggested Queries**: For each gap, provide 2-3 specific search queries that would help fill the gap.

4. **Priority Categories**: Which categories are most critical to fill first?

5. **Sufficient**: Is the research sufficient to proceed with idea generation? (true/false)

Return as JSON:
{{
  "coverage_score": 65,
  "gaps": [
    {{
      "category": "03-consumidor",
      "gap_description": "Missing specific insights about target's coffee consumption habits",
      "importance": "Critical for developing relevant creative concepts",
      "suggested_queries": [
        "coffee consumption habits young professionals Paraguay",
        "when do millennials drink coffee Paraguay"
      ]
    }}
  ],
  "priority_categories": ["03-consumidor", "02-competencia"],
  "sufficient": false,
  "recommendation": "Need at least 2-3 more sources in consumer insights and competitor analysis"
}}"""

            response = await self.ai_manager.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=2000
            )

            # Parse response
            result = self._parse_json_response(response)
            result["total_sources"] = total_sources
            result["category_coverage"] = category_coverage

            logger.info(f"Research gap analysis complete: {result['coverage_score']}% coverage")
            return result

        except Exception as e:
            logger.error(f"Research gap analysis failed: {e}")
            raise IterationError(f"Failed to analyze research gaps: {e}")

    async def generate_search_queries(
        self,
        project_id: str,
        focus_areas: list[str] = None,
        num_queries: int = 10
    ) -> dict:
        """
        Generate search queries based on brief and research gaps.

        Args:
            project_id: Project identifier
            focus_areas: Specific categories to focus on
            num_queries: Number of queries to generate

        Returns:
            Dict with categorized search queries
        """
        try:
            project_dir = self.file_ops.get_project_path(project_id)

            # Load brief
            brief_path = project_dir / "brief-expanded.md"
            brief_content = ""
            if brief_path.exists():
                brief_content = brief_path.read_text(encoding="utf-8")

            # Load project metadata for country
            project_meta = self.file_ops.get_project_metadata(project_id)
            country = project_meta.get("country", "Paraguay")

            # Focus areas filter
            focus_text = ""
            if focus_areas:
                focus_text = f"\n\nFocus primarily on these categories: {', '.join(focus_areas)}"

            prompt = f"""Generate search queries to research this marketing campaign.

## Campaign Brief
{brief_content[:3000] if brief_content else "No brief available"}

## Target Country
{country}

## Research Categories Available
{json.dumps(self.RESEARCH_CATEGORIES, indent=2)}
{focus_text}

## Task
Generate {num_queries} specific, actionable search queries that will help build comprehensive research for this campaign.

Requirements:
- Queries should be in Spanish (primary) and English (for international sources)
- Include the country name where relevant
- Be specific enough to find useful results
- Cover different aspects: market data, consumer insights, competitors, trends
- Assign each query to the most appropriate research category

Return as JSON:
{{
  "queries": [
    {{
      "query": "mercado café Paraguay 2024 tamaño crecimiento",
      "query_en": "coffee market Paraguay 2024 size growth",
      "category": "01-mercado-general",
      "expected_insights": "Market size, growth rate, key players"
    }},
    {{
      "query": "Starbucks Juan Valdez Paraguay competencia",
      "query_en": "Starbucks Juan Valdez Paraguay competition",
      "category": "02-competencia",
      "expected_insights": "Competitor positioning, market share"
    }}
  ],
  "search_strategy": "Start with market overview, then deep-dive into consumer behavior"
}}"""

            response = await self.ai_manager.generate(
                prompt=prompt,
                temperature=0.5,
                max_tokens=2000
            )

            result = self._parse_json_response(response)
            logger.info(f"Generated {len(result.get('queries', []))} search queries")
            return result

        except Exception as e:
            logger.error(f"Search query generation failed: {e}")
            raise IterationError(f"Failed to generate search queries: {e}")

    async def analyze_idea_gaps(self, project_id: str) -> dict:
        """
        Analyze idea quality and identify areas for improvement.

        Returns:
            Dict with quality analysis, gaps, and improvement suggestions
        """
        try:
            project_dir = self.file_ops.get_project_path(project_id)

            # Load ideas summary
            summary_path = project_dir / "ideas-summary.md"
            summary_content = ""
            if summary_path.exists():
                summary_content = summary_path.read_text(encoding="utf-8")

            # Load all ideas for detailed analysis
            ideas_dir = project_dir / "ideas"
            ideas = []
            if ideas_dir.exists():
                for idea_file in sorted(ideas_dir.glob("idea-*.md")):
                    content = idea_file.read_text(encoding="utf-8")
                    ideas.append({
                        "file": idea_file.name,
                        "content": content[:1500]  # Truncate for context
                    })

            # Load brief for context
            brief_path = project_dir / "brief-expanded.md"
            brief_content = ""
            if brief_path.exists():
                brief_content = brief_path.read_text(encoding="utf-8")

            prompt = f"""Analyze the campaign ideas and identify gaps and improvement opportunities.

## Brief Summary
{brief_content[:2000] if brief_content else "No brief available"}

## Ideas Summary
{summary_content[:3000] if summary_content else "No summary available"}

## Number of Ideas
{len(ideas)} ideas generated

## Task
Analyze the ideas portfolio and provide:

1. **Quality Distribution**: How many ideas are in each tier (Tier 1-5)?

2. **Scoring Patterns**: Which scoring dimensions are consistently weak?
   - Diferenciación, Relevancia Cultural, Claridad Insight, Ejecutabilidad
   - Potencial Viral, Memorabilidad, Versatilidad, Alineación Marca
   - Potencial PR, Escalabilidad

3. **Coverage Gaps**:
   - Which creative directions from the brief are underrepresented?
   - What types of ideas are missing (digital, experiential, PR, etc.)?

4. **Improvement Opportunities**:
   - Which low-tier ideas have potential if refined?
   - What specific improvements would raise scores?

5. **Recommendations**:
   - Should we generate more ideas? How many?
   - What should the focus be for new ideas?
   - Are there ideas to combine or merge?

Return as JSON:
{{
  "tier_distribution": {{
    "tier_1": 2,
    "tier_2": 5,
    "tier_3": 8,
    "tier_4": 7,
    "tier_5": 3
  }},
  "weak_dimensions": [
    {{
      "dimension": "potencial_viral",
      "average_score": 5.2,
      "improvement_suggestion": "Add shareable mechanics and social hooks"
    }}
  ],
  "coverage_gaps": [
    {{
      "gap_type": "Missing PR-focused ideas",
      "importance": "High - brief emphasizes earned media",
      "suggestion": "Generate ideas with newsworthy hooks"
    }}
  ],
  "combinable_ideas": [
    {{
      "idea_numbers": [3, 7, 15],
      "reason": "Similar insights, could merge into stronger concept"
    }}
  ],
  "recommendations": {{
    "generate_more": true,
    "num_additional": 10,
    "focus_areas": ["viral_potential", "PR_hooks"],
    "overall_quality": "Moderate - need more Tier 1-2 ideas"
  }},
  "quality_score": 65
}}"""

            response = await self.ai_manager.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=2000
            )

            result = self._parse_json_response(response)
            result["total_ideas"] = len(ideas)

            logger.info(f"Idea gap analysis complete: quality score {result.get('quality_score', 0)}")
            return result

        except Exception as e:
            logger.error(f"Idea gap analysis failed: {e}")
            raise IterationError(f"Failed to analyze idea gaps: {e}")

    async def generate_targeted_ideas(
        self,
        project_id: str,
        focus: str,
        avoid_similar_to: list[int] = None,
        num_ideas: int = 10
    ) -> dict:
        """
        Generate ideas focused on specific dimensions or gaps.

        Args:
            project_id: Project identifier
            focus: What to focus on (e.g., "viral_potential", "PR_hooks")
            avoid_similar_to: Idea numbers to avoid duplicating
            num_ideas: Number of ideas to generate

        Returns:
            Dict with new ideas and metadata
        """
        try:
            project_dir = self.file_ops.get_project_path(project_id)

            # Load context
            brief_path = project_dir / "brief-expanded.md"
            brief_content = brief_path.read_text(encoding="utf-8") if brief_path.exists() else ""

            quick_ref_path = project_dir / "quick-reference.md"
            quick_ref = quick_ref_path.read_text(encoding="utf-8") if quick_ref_path.exists() else ""

            # Load existing ideas to avoid duplication
            ideas_dir = project_dir / "ideas"
            existing_titles = []
            if ideas_dir.exists():
                for idea_file in ideas_dir.glob("idea-*.md"):
                    content = idea_file.read_text(encoding="utf-8")
                    # Extract title from first line
                    first_line = content.split('\n')[0]
                    if first_line.startswith('#'):
                        existing_titles.append(first_line.strip('# '))

            # Get next idea number
            next_number = len(existing_titles) + 1

            prompt = f"""Generate {num_ideas} campaign ideas with a specific focus.

## Brief
{brief_content[:2000]}

## Quick Reference
{quick_ref[:1500]}

## SPECIFIC FOCUS
Generate ideas that excel in: **{focus}**

This means:
- If focus is "viral_potential": Ideas with shareable hooks, social mechanics, user participation
- If focus is "PR_hooks": Newsworthy concepts, controversy, first-evers, celebrity potential
- If focus is "cultural_relevance": Deep local insights, traditions, social movements
- If focus is "memorability": Distinctive visuals, catchy concepts, emotional hooks

## Existing Ideas (DO NOT DUPLICATE)
{json.dumps(existing_titles[:20], indent=2)}

## Task
Generate {num_ideas} new, distinct campaign ideas that specifically address the focus area.
Each idea should score high (8+) on the focus dimension.

Return as JSON:
{{
  "ideas": [
    {{
      "number": {next_number},
      "title": "Unique, catchy title",
      "concept": "2-3 sentence concept description",
      "insight": "The human truth behind the idea",
      "why_high_score": "Why this idea excels in {focus}",
      "formats": ["Social", "OOH", "Activation"]
    }}
  ],
  "focus_addressed": "{focus}",
  "differentiation_notes": "How these differ from existing ideas"
}}"""

            response = await self.ai_manager.generate(
                prompt=prompt,
                temperature=0.8,  # Higher for creativity
                max_tokens=3000
            )

            result = self._parse_json_response(response)

            # Save the new ideas
            saved_ideas = []
            ideas_dir.mkdir(parents=True, exist_ok=True)

            for idea in result.get("ideas", []):
                idea_number = idea.get("number", next_number)
                idea_filename = f"idea-{idea_number:03d}.md"
                idea_path = ideas_dir / idea_filename

                idea_content = f"""# {idea.get('title', 'Untitled')}

## Concept
{idea.get('concept', '')}

## Insight
{idea.get('insight', '')}

## Focus: {focus}
{idea.get('why_high_score', '')}

## Formats
{', '.join(idea.get('formats', []))}

---
*Generated as targeted idea focusing on {focus}*
"""
                idea_path.write_text(idea_content, encoding="utf-8")
                saved_ideas.append(idea_filename)
                next_number += 1

            result["saved_files"] = saved_ideas
            result["total_ideas_now"] = next_number - 1

            logger.info(f"Generated {len(saved_ideas)} targeted ideas focusing on {focus}")
            return result

        except Exception as e:
            logger.error(f"Targeted idea generation failed: {e}")
            raise IterationError(f"Failed to generate targeted ideas: {e}")

    async def combine_ideas(
        self,
        project_id: str,
        idea_numbers: list[int],
        direction: str = None
    ) -> dict:
        """
        Combine multiple ideas into a stronger unified concept.

        Args:
            project_id: Project identifier
            idea_numbers: List of idea numbers to combine
            direction: Optional guidance for combination

        Returns:
            Dict with new combined idea
        """
        try:
            project_dir = self.file_ops.get_project_path(project_id)
            ideas_dir = project_dir / "ideas"

            # Load the ideas to combine
            ideas_content = []
            for num in idea_numbers:
                idea_path = ideas_dir / f"idea-{num:03d}.md"
                if idea_path.exists():
                    content = idea_path.read_text(encoding="utf-8")
                    ideas_content.append(f"### Idea {num}\n{content}")

            if not ideas_content:
                raise IterationError(f"No ideas found for numbers: {idea_numbers}")

            # Get next idea number
            existing_ideas = list(ideas_dir.glob("idea-*.md"))
            next_number = len(existing_ideas) + 1

            direction_text = f"\nDirection: {direction}" if direction else ""

            prompt = f"""Combine these campaign ideas into a single, stronger concept.

## Ideas to Combine
{chr(10).join(ideas_content)}
{direction_text}

## Task
Analyze each idea and create a new concept that:
- Takes the best elements from each
- Resolves any contradictions
- Creates a coherent, unified idea
- Is stronger than any individual component

Return as JSON:
{{
  "combined_idea": {{
    "number": {next_number},
    "title": "New unified title",
    "concept": "Merged concept description",
    "insight": "Combined human truth",
    "elements_from_each": {{
      "idea_X": "What was taken from idea X",
      "idea_Y": "What was taken from idea Y"
    }},
    "formats": ["Format1", "Format2"],
    "improvement_notes": "Why this combination is stronger"
  }},
  "combination_rationale": "Why these ideas work well together"
}}"""

            response = await self.ai_manager.generate(
                prompt=prompt,
                temperature=0.6,
                max_tokens=1500
            )

            result = self._parse_json_response(response)

            # Save the combined idea
            combined = result.get("combined_idea", {})
            idea_filename = f"idea-{next_number:03d}.md"
            idea_path = ideas_dir / idea_filename

            elements_text = "\n".join([
                f"- From Idea {k.split('_')[1]}: {v}"
                for k, v in combined.get("elements_from_each", {}).items()
            ])

            idea_content = f"""# {combined.get('title', 'Combined Idea')}

## Concept
{combined.get('concept', '')}

## Insight
{combined.get('insight', '')}

## Elements Combined
{elements_text}

## Formats
{', '.join(combined.get('formats', []))}

## Why This Works
{combined.get('improvement_notes', '')}

---
*Combined from ideas: {', '.join(map(str, idea_numbers))}*
"""
            idea_path.write_text(idea_content, encoding="utf-8")

            result["saved_file"] = idea_filename
            result["new_idea_number"] = next_number
            result["combined_from"] = idea_numbers

            logger.info(f"Combined ideas {idea_numbers} into idea {next_number}")
            return result

        except Exception as e:
            logger.error(f"Idea combination failed: {e}")
            raise IterationError(f"Failed to combine ideas: {e}")

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from AI response, handling markdown code blocks."""
        try:
            # Remove markdown code blocks if present
            text = response.strip()
            if text.startswith("```"):
                lines = text.split('\n')
                # Remove first and last lines (```json and ```)
                text = '\n'.join(lines[1:-1])

            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            # Return a default structure
            return {"error": "Failed to parse response", "raw": response[:500]}


# Singleton
_iteration_service: IterationService | None = None


def get_iteration_service() -> IterationService:
    """Get singleton iteration service."""
    global _iteration_service
    if _iteration_service is None:
        _iteration_service = IterationService()
    return _iteration_service
