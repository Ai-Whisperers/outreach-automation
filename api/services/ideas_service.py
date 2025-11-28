"""
Ideas Generation Service

Generates, expands, scores, and ranks campaign ideas.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..logging_config import get_logger
from ..models import (
    CulturalValidation,
    IdeaConcept,
    IdeaExpanded,
    IdeaExpandResponse,
    IdeaGenerateResponse,
    IdeaScoreResponse,
    IdeaScores,
    IdeaSummary,
    QualityValidation,
)
from ..utils.similarity import check_idea_similarity
from .ai_client import get_ai_manager, get_prompt_loader
from .file_operations import get_file_service
from .research_service import get_research_service
from .template_renderer import get_template_renderer

logger = get_logger("ideas_service")
settings = get_settings()


# =============================================================================
# Ideas Service
# =============================================================================

class IdeasService:
    """
    Service for generating, expanding, and scoring campaign ideas.
    """

    def __init__(self, idea_repository: Any | None = None):
        self.ai = get_ai_manager()
        self.prompts = get_prompt_loader()
        self.files = get_file_service()
        self.renderer = get_template_renderer()
        self.research = get_research_service()
        self.config = get_settings()
        self.idea_repository = idea_repository

    async def generate_ideas(
        self,
        project_id: str,
        num_ideas: int = 25,
        batch_size: int = 5,
        creative_directions: list[str] | None = None
    ) -> IdeaGenerateResponse:
        """
        Generate campaign idea concepts.

        Args:
            project_id: Project identifier
            num_ideas: Total number of ideas to generate
            batch_size: Ideas per AI call
            creative_directions: Optional specific directions to explore

        Returns:
            Response with generated concepts
        """
        logger.info(f"Generating {num_ideas} ideas for project: {project_id}")

        # Check if LangGraph v2 is enabled
        if settings.use_langgraph_v2:
            logger.info("[v2] Using LangGraph for idea generation")
            return await self._generate_ideas_v2(project_id, num_ideas, batch_size)

        # Fall back to legacy v1 implementation
        logger.info("[v1] Using legacy idea generation")

        # Get context
        research_content = await self.research.get_all_research(project_id)

        # Try to get quick reference
        try:
            quick_ref = await self.files.read_file(project_id, "quick-reference.md")
        except Exception:
            quick_ref = ""

        # Try to get brief
        try:
            brief = await self.files.read_file(project_id, "brief-original.md")
        except Exception:
            brief = ""

        # Generate in batches
        all_concepts = []
        num_batches = (num_ideas + batch_size - 1) // batch_size

        for batch_num in range(num_batches):
            remaining = num_ideas - len(all_concepts)
            current_batch_size = min(batch_size, remaining)

            if current_batch_size <= 0:
                break

            logger.debug(f"Generating batch {batch_num + 1}/{num_batches}")

            concepts = await self._generate_batch(
                research_content=research_content,
                quick_reference=quick_ref,
                brief=brief,
                num_ideas=current_batch_size,
                existing_ideas=[c.title for c in all_concepts],
                creative_directions=creative_directions
            )

            # Assign numbers
            for concept in concepts:
                concept.number = len(all_concepts) + 1
                all_concepts.append(concept)

        # Get metadata for expansion
        metadata = self.files.get_project_metadata(project_id)
        country = metadata.get("country", "Paraguay")

        # Expand and save each idea
        files_created = []
        # Expand and save each idea
        files_created = []

        # Use semaphore to limit concurrency and avoid rate limits
        sem = asyncio.Semaphore(5)  # Allow 5 concurrent expansions

        async def expand_and_save(concept):
            async with sem:
                try:
                    # Expand the idea
                    expanded = await self._expand_single_idea(
                        concept=concept,
                        brief=brief,
                        quick_reference=quick_ref,
                        country=country
                    )
                    expanded.number = concept.number

                    # Validate quality
                    quality = await self._validate_quality(expanded)

                    # Validate cultural relevance
                    cultural = await self._validate_cultural(expanded, country)

                    # Calculate scores
                    scores_dict = {
                        "diferenciacion": expanded.scores.diferenciacion,
                        "relevancia_cultural": cultural.cultural_score,
                        "claridad_insight": expanded.scores.claridad_insight,
                        "ejecutabilidad": expanded.scores.ejecutabilidad,
                        "potencial_viral": expanded.scores.potencial_viral,
                        "memorabilidad": expanded.scores.memorabilidad,
                        "versatilidad": expanded.scores.versatilidad,
                        "alineacion_marca": expanded.scores.alineacion_marca,
                        "potencial_pr": expanded.scores.potencial_pr,
                        "escalabilidad": expanded.scores.escalabilidad
                    }

                    # Update cultural score
                    expanded.scores.relevancia_cultural = cultural.cultural_score

                    # Calculate weighted score
                    overall = self._calculate_weighted_score(scores_dict)
                    expanded.overall_score = round(overall, 1)
                    expanded.tier = self._get_tier(expanded.overall_score)

                    # Merge strengths/weaknesses
                    expanded.strengths = list(set(expanded.strengths + quality.strengths + cultural.positives))
                    expanded.weaknesses = list(set(expanded.weaknesses + quality.weaknesses + cultural.concerns))

                    # Render and save
                    rendered = self.renderer.render_idea(
                        idea_number=expanded.number,
                        title=expanded.title,
                        concept=expanded.concept,
                        insight=expanded.insight,
                        execution=expanded.execution,
                        scores=scores_dict,
                        overall_score=expanded.overall_score,
                        tier=expanded.tier,
                        strengths=expanded.strengths,
                        weaknesses=expanded.weaknesses,
                        recommendation=expanded.recommendation
                    )

                    file_path = await self.files.save_idea(project_id, expanded.number, rendered)

                    # Save to database if repository available
                    if self.idea_repository:
                        try:
                            import json
                            from datetime import datetime

                            from ..database.models import Idea

                            db_idea = Idea(
                                project_id=project_id,
                                number=expanded.number,
                                title=expanded.title,
                                file_path=str(file_path),
                                overall_score=expanded.overall_score,
                                tier=expanded.tier,
                                scores_json=json.dumps(scores_dict),
                                created_at=datetime.utcnow()
                            )
                            await self.idea_repository.create(db_idea)
                            logger.debug(f"Saved idea {expanded.number} to database")
                        except Exception as e:
                            logger.warning(f"Failed to save idea to database: {e}")

                    logger.debug(f"Expanded and saved idea {expanded.number}: {expanded.title}")
                    return str(file_path)

                except Exception as e:
                    logger.error(f"Failed to expand idea {concept.number}: {e}")
                    return None

        # Run expansions in parallel
        results = await asyncio.gather(*[expand_and_save(c) for c in all_concepts])
        files_created = [r for r in results if r is not None]

        # Update project status
        self.files.update_project_metadata(project_id, {
            "status": "ideas_generated",
            "ideas_count": len(all_concepts)
        })

        logger.info(f"Generated and saved {len(files_created)} ideas for project: {project_id}")

        return IdeaGenerateResponse(
            project_id=project_id,
            ideas_generated=len(all_concepts),
            concepts=all_concepts,
            files_created=[f.split("/")[-1].split("\\")[-1] for f in files_created]
        )


    async def _generate_batch(
        self,
        research_content: str,
        quick_reference: str,
        brief: str,
        num_ideas: int,
        existing_ideas: list[str],
        creative_directions: list[str] | None
    ) -> list[IdeaConcept]:
        """Generate a batch of idea concepts."""

        # Build context
        context = f"""
BRIEF:
{brief[:2000] if brief else "No brief available"}

QUICK REFERENCE:
{quick_reference[:3000] if quick_reference else "No quick reference available"}

RESEARCH SUMMARY:
{research_content[:5000] if research_content else "No research available"}
"""

        existing_str = "\n".join(f"- {idea}" for idea in existing_ideas) if existing_ideas else "None"
        directions_str = ", ".join(creative_directions) if creative_directions else "Any creative direction"

        system, user = self.prompts.format(
            "ideas", "generate",
            context=context,
            num_ideas=num_ideas,
            existing_ideas=existing_str,
            creative_directions=directions_str
        )

        response = await self.ai.generate_json(
            prompt=user,
            system=system,
            temperature=0.8  # Higher for creativity
        )

        concepts = []

        # Convert existing ideas to dict format for similarity check
        existing_dicts = [{"title": t} for t in existing_ideas]

        for idea in response.get("ideas", []):
            title = idea.get("title") or idea.get("name") or "Untitled"
            logger.info(f"Processing idea: {title}")

            # Check for similarity
            is_similar, score, similar_to = check_idea_similarity(
                idea,
                existing_dicts,
                threshold=0.6  # Slightly higher threshold for batch generation
            )

            if is_similar:
                logger.info(f"Skipping similar idea: '{title}' (similar to '{similar_to}', score: {score:.2f})")
                continue

            logger.info(f"Adding idea: {title}")
            concepts.append(IdeaConcept(
                number=0,  # Will be assigned later
                title=title,
                concept=idea.get("concept", ""),
                insight=idea.get("insight", ""),
                formats=idea.get("formats", [])
            ))

            # Add to existing dicts so we don't generate duplicates within the same batch
            existing_dicts.append(idea)

        logger.info(f"Returning {len(concepts)} concepts")
        return concepts

    async def expand_idea(
        self,
        project_id: str,
        idea_number: int,
        concept: IdeaConcept | None = None
    ) -> IdeaExpandResponse:
        """
        Expand an idea with full details and scoring.

        Args:
            project_id: Project identifier
            idea_number: Idea number to expand
            concept: Optional concept (if not provided, loads from file)

        Returns:
            Expanded idea with scores
        """
        logger.info(f"Expanding idea {idea_number} for project: {project_id}")

        # Get context
        metadata = self.files.get_project_metadata(project_id)

        try:
            brief = await self.files.read_file(project_id, "brief-original.md")
        except Exception:
            brief = ""

        try:
            quick_ref = await self.files.read_file(project_id, "quick-reference.md")
        except Exception:
            quick_ref = ""

        # Expand the idea
        expanded = await self._expand_single_idea(
            concept=concept,
            brief=brief,
            quick_reference=quick_ref,
            country=metadata.get("country", "Paraguay")
        )
        expanded.number = idea_number

        # Validate quality
        quality = await self._validate_quality(expanded)

        # Validate cultural relevance
        cultural = await self._validate_cultural(
            expanded,
            metadata.get("country", "Paraguay")
        )

        # Calculate final score
        scores_dict = {
            "diferenciacion": expanded.scores.diferenciacion,
            "relevancia_cultural": cultural.cultural_score,
            "claridad_insight": expanded.scores.claridad_insight,
            "ejecutabilidad": expanded.scores.ejecutabilidad,
            "potencial_viral": expanded.scores.potencial_viral,
            "memorabilidad": expanded.scores.memorabilidad,
            "versatilidad": expanded.scores.versatilidad,
            "alineacion_marca": expanded.scores.alineacion_marca,
            "potencial_pr": expanded.scores.potencial_pr,
            "escalabilidad": expanded.scores.escalabilidad
        }

        # Update cultural score
        expanded.scores.relevancia_cultural = cultural.cultural_score

        # Calculate weighted score
        overall = self._calculate_weighted_score(scores_dict)
        expanded.overall_score = round(overall, 1)

        # Determine tier
        expanded.tier = self._get_tier(expanded.overall_score)

        # Merge strengths/weaknesses from validations
        expanded.strengths = list(set(expanded.strengths + quality.strengths + cultural.positives))
        expanded.weaknesses = list(set(expanded.weaknesses + quality.weaknesses + cultural.concerns))

        # Render and save
        rendered = self.renderer.render_idea(
            idea_number=expanded.number,
            title=expanded.title,
            concept=expanded.concept,
            insight=expanded.insight,
            execution=expanded.execution,
            scores=scores_dict,
            overall_score=expanded.overall_score,
            tier=expanded.tier,
            strengths=expanded.strengths,
            weaknesses=expanded.weaknesses,
            recommendation=expanded.recommendation
        )

        file_path = await self.files.save_idea(project_id, idea_number, rendered)

        logger.info(f"Expanded idea {idea_number} with score {expanded.overall_score}")

        return IdeaExpandResponse(
            project_id=project_id,
            idea=expanded,
            file_path=str(file_path)
        )

    async def _expand_single_idea(
        self,
        concept: IdeaConcept,
        brief: str,
        quick_reference: str,
        country: str
    ) -> IdeaExpanded:
        """Expand a single idea concept to full detail."""

        system, user = self.prompts.format(
            "ideas", "expand",
            title=concept.title,
            concept=concept.concept,
            insight=concept.insight,
            formats=", ".join(concept.formats),
            brief=brief[:2000],
            quick_reference=quick_reference[:2000],
            country=country
        )

        response = await self.ai.generate_json(
            prompt=user,
            system=system,
            temperature=0.6
        )

        # Parse scores
        scores_data = response.get("scores", {})
        scores = IdeaScores(
            diferenciacion=scores_data.get("diferenciacion", 5),
            relevancia_cultural=scores_data.get("relevancia_cultural", 5),
            claridad_insight=scores_data.get("claridad_insight", 5),
            ejecutabilidad=scores_data.get("ejecutabilidad", 5),
            potencial_viral=scores_data.get("potencial_viral", 5),
            memorabilidad=scores_data.get("memorabilidad", 5),
            versatilidad=scores_data.get("versatilidad", 5),
            alineacion_marca=scores_data.get("alineacion_marca", 5),
            potencial_pr=scores_data.get("potencial_pr", 5),
            escalabilidad=scores_data.get("escalabilidad", 5)
        )

        return IdeaExpanded(
            number=0,
            title=concept.title,
            concept=response.get("concept", concept.concept),
            insight=response.get("insight", concept.insight),
            execution=response.get("execution", {}),
            scores=scores,
            overall_score=0,  # Will be calculated
            tier="",  # Will be determined
            strengths=response.get("strengths", []),
            weaknesses=response.get("weaknesses", []),
            recommendation=response.get("recommendation", "")
        )

    async def _validate_quality(self, idea: IdeaExpanded) -> QualityValidation:
        """Validate idea quality."""

        idea_content = f"""
Title: {idea.title}
Concept: {idea.concept}
Insight: {idea.insight}
Execution: {idea.execution}
"""

        system, user = self.prompts.format(
            "quality", "validate",
            idea_content=idea_content
        )

        response = await self.ai.generate_json(
            prompt=user,
            system=system,
            temperature=0.3
        )

        return QualityValidation(
            scores=response.get("scores", {}),
            overall=response.get("overall", 5),
            strengths=response.get("strengths", []),
            weaknesses=response.get("weaknesses", []),
            suggestions=response.get("suggestions", [])
        )

    async def _validate_cultural(
        self,
        idea: IdeaExpanded,
        country: str
    ) -> CulturalValidation:
        """Validate cultural relevance."""

        idea_content = f"""
Title: {idea.title}
Concept: {idea.concept}
Insight: {idea.insight}
"""

        system, user = self.prompts.format(
            "quality", "cultural",
            idea_content=idea_content,
            country=country
        )

        response = await self.ai.generate_json(
            prompt=user,
            system=system,
            temperature=0.3
        )

        return CulturalValidation(
            cultural_score=response.get("cultural_score", 5),
            positives=response.get("positives", []),
            concerns=response.get("concerns", []),
            suggestions=response.get("suggestions", []),
            approved=response.get("approved", True)
        )

    def _calculate_weighted_score(self, scores: dict[str, float]) -> float:
        """Calculate weighted average score using config weights."""
        # Load weights from config
        config = get_settings()

        # Build weights dict from config criteria
        # Normalize names: "Diferenciación" -> "diferenciacion"
        weights = {}
        for criterion in config.scoring.criteria:
            # Convert to lowercase and replace spaces/accents
            key = criterion.name.lower()
            key = key.replace("á", "a").replace("é", "e").replace("í", "i")
            key = key.replace("ó", "o").replace("ú", "u")
            key = key.replace(" ", "_").replace("-", "_")
            # Map common names
            key_mappings = {
                "diferenciacion": "diferenciacion",
                "relevancia_cultural": "relevancia_cultural",
                "claridad_del_insight": "claridad_insight",
                "ejecutabilidad": "ejecutabilidad",
                "potencial_viral": "potencial_viral",
                "memorabilidad": "memorabilidad",
                "versatilidad": "versatilidad",
                "alineacion_con_marca": "alineacion_marca",
                "potencial_pr": "potencial_pr",
                "escalabilidad": "escalabilidad"
            }
            normalized_key = key_mappings.get(key, key)
            weights[normalized_key] = criterion.weight

        total_weight = 0
        weighted_sum = 0

        for criterion, score in scores.items():
            weight = weights.get(criterion, 1.0)
            weighted_sum += score * weight
            total_weight += weight

        if total_weight == 0:
            return 0

        return (weighted_sum / total_weight)

    def _get_tier(self, score: float) -> str:
        """Get tier classification from score."""
        if score >= 9.0:
            return "Tier 1 - Idea Excepcional"
        elif score >= 8.0:
            return "Tier 2 - Idea Sólida"
        elif score >= 7.0:
            return "Tier 3 - Idea Promisoria"
        elif score >= 6.0:
            return "Tier 4 - Necesita Trabajo"
        else:
            return "Tier 5 - Reconsiderar"

    async def score_all_ideas(
        self,
        project_id: str,
        recalculate: bool = False
    ) -> IdeaScoreResponse:
        """
        Score and rank all ideas in a project.

        Args:
            project_id: Project identifier
            recalculate: Whether to recalculate existing scores

        Returns:
            Scoring response with rankings
        """
        logger.info(f"Scoring all ideas for project: {project_id}")

        idea_files = self.files.get_idea_files(project_id)
        ideas_summary = []
        tier_distribution = {
            "Tier 1": 0,
            "Tier 2": 0,
            "Tier 3": 0,
            "Tier 4": 0,
            "Tier 5": 0
        }

        for file_path in idea_files:
            # Extract idea number from filename
            filename = Path(file_path).name
            logger.info(f"Processing idea file: {file_path}")
            try:
                # Extract idea number from filename
                try:
                    idea_num = int(filename.replace("idea-", "").replace(".md", ""))
                except ValueError:
                    logger.warning(f"Could not extract idea number from filename: {filename}. Skipping.")
                    continue

                # Read idea content and extract score
                content = await self.files.read_file(project_id, file_path)
                logger.info(f"Read content length: {len(content)}")

                # Parse score from markdown (simple extraction)
                score = self._extract_score_from_markdown(content)
                tier = self._get_tier(score)
                title = self._extract_title_from_markdown(content)

                ideas_summary.append(IdeaSummary(
                    number=idea_num,
                    title=title,
                    overall_score=score,
                    tier=tier
                ))

                # Update tier distribution
                tier_key = tier.split(" - ")[0]
                if tier_key in tier_distribution:
                    tier_distribution[tier_key] += 1
            except Exception as e:
                logger.error(f"Error processing idea file {file_path}: {e}")
                continue





        # Sort by score
        ideas_summary.sort(key=lambda x: x.overall_score, reverse=True)

        # Generate summary file
        top_ideas = ideas_summary[:10]
        recommendations = self._generate_recommendations(ideas_summary)

        summary_content = self.renderer.render_ideas_summary(
            project_name=self.files.get_project_metadata(project_id).get("name", ""),
            total_ideas=len(ideas_summary),
            ideas=[
                {
                    "number": i.number,
                    "name": i.title,
                    "score": i.overall_score,
                    "tier": i.tier
                }
                for i in ideas_summary
            ],
            top_ideas=[
                {
                    "number": i.number,
                    "name": i.title,
                    "score": i.overall_score,
                    "tier": i.tier
                }
                for i in top_ideas
            ],
            tier_distribution=tier_distribution,
            recommendations=recommendations
        )

        await self.files.write_file(project_id, "ideas-summary.md", summary_content)

        # Update project status
        self.files.update_project_metadata(project_id, {
            "status": "ideas_scored",
            "top_score": top_ideas[0].overall_score if top_ideas else 0
        })

        logger.info(f"Scored {len(ideas_summary)} ideas for project: {project_id}")

        return IdeaScoreResponse(
            project_id=project_id,
            total_ideas=len(ideas_summary),
            tier_distribution=tier_distribution,
            top_ideas=top_ideas,
            summary_file="ideas-summary.md"
        )

    async def _generate_ideas_v2(
        self,
        project_id: str,
        num_ideas: int = 15,
        batch_size: int = 5
    ) -> IdeaGenerateResponse:
        """
        Generate ideas using LangGraph v2 with parallel research.

        Args:
            project_id: Project identifier
            num_ideas: Total number of ideas to generate
            batch_size: Not used in v2 (always generates in batches of 5)

        Returns:
            Response with generated concepts
        """
        from datetime import datetime

        from ..graphs import CampaignGraphRunner

        logger.info(f"[LangGraph v2] Generating {num_ideas} ideas for {project_id}")

        try:
            # Initialize campaign graph runner
            runner = CampaignGraphRunner()

            # Run the campaign workflow
            final_state = await runner.run_campaign(project_id, num_ideas)

            # Save ideas to disk in v1 format
            # Handle relative paths from code/ directory
            projects_base = str(settings.projects_dir)
            if not os.path.isabs(projects_base) and not os.path.exists(projects_base):
                # Try parent directory (for when running from code/)
                projects_base = os.path.join("..", projects_base)

            ideas_dir = os.path.join(projects_base, project_id, "ideas")
            os.makedirs(ideas_dir, exist_ok=True)

            saved_concepts = []

            for idea in final_state.get("scored_ideas", []):
                # Save markdown file
                filename = f"{ideas_dir}/{idea['id']}.md"

                content = f"""# {idea['title']}

## Concepto
**Headline**: {idea['headline']}

## Descripción
{idea['description']}

## Rationale
{idea['rationale']}

## Plan de Ejecución
{chr(10).join(f"{i+1}. {tactic}" for i, tactic in enumerate(idea['execution']))}

## Scores
- **Relevancia**: {idea['scores'].get('relevance', 0)}/10
- **Creatividad**: {idea['scores'].get('creativity', 0)}/10
- **Viabilidad**: {idea['scores'].get('feasibility', 0)}/10
- **Impacto**: {idea['scores'].get('impact', 0)}/10
- **Score General**: {idea.get('overall_score', 0):.1f}/10

### Feedback
{idea['scores'].get('feedback', 'No feedback available')}

---

*Generado con LangGraph v2 - {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""

                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)

                # Convert to IdeaConcept for compatibility
                # Extract idea number from ID (e.g., "idea-001" -> 1)
                idea_number = int(idea['id'].split('-')[-1]) if '-' in idea['id'] else len(saved_concepts) + 1

                concept = IdeaConcept(
                    number=idea_number,
                    title=idea['title'],
                    concept=idea['description'],
                    insight=idea['rationale'],  # Use rationale as insight
                    formats=["Digital", "Social Media"]  # Default formats for v2
                )

                saved_concepts.append(concept)

            logger.info(f"[LangGraph v2] Successfully generated and saved {len(saved_concepts)} ideas")

            # Return response in v1 format
            return IdeaGenerateResponse(
                project_id=project_id,
                ideas_generated=len(saved_concepts),
                concepts=saved_concepts,
                files_created=[f"ideas/{c.number:03d}.md" for c in saved_concepts]
            )

        except Exception as e:
            logger.error(f"[LangGraph v2] Error generating ideas: {e}", exc_info=True)
            # Fall back to v1 on error
            logger.warning("[LangGraph v2] Falling back to v1 implementation due to error")
            # Remove the v2 check to prevent infinite loop
            old_setting = settings.use_langgraph_v2
            settings.use_langgraph_v2 = False
            try:
                result = await self.generate_ideas(project_id, num_ideas, batch_size)
                return result
            finally:
                settings.use_langgraph_v2 = old_setting

    def _extract_score_from_markdown(self, content: str) -> float:
        """Extract overall score from idea markdown."""
        # Look for "Promedio Ponderado" or "Overall Score"
        for line in content.split("\n"):
            if "Promedio" in line or "Overall" in line or "**Promedio" in line:
                # Extract number
                import re
                match = re.search(r"(\d+\.?\d*)", line)
                if match:
                    return float(match.group(1))
        return 5.0

    def _extract_title_from_markdown(self, content: str) -> str:
        """Extract title from idea markdown."""
        for line in content.split("\n"):
            if line.startswith("# "):
                return line.replace("# ", "").strip()
        return "Untitled"

    def _generate_recommendations(self, ideas: list[IdeaSummary]) -> list[str]:
        """Generate recommendations based on idea scores."""
        recommendations = []

        if not ideas:
            recommendations.append("No hay ideas para evaluar.")
            return recommendations

        top_score = ideas[0].overall_score if ideas else 0
        avg_score = sum(i.overall_score for i in ideas) / len(ideas)

        if top_score >= 8.5:
            recommendations.append(
                f"La idea '{ideas[0].title}' es excepcional y debería ser la prioridad principal."
            )

        if avg_score < 7.0:
            recommendations.append(
                "El promedio general es bajo. Considerar generar más ideas o refinar las existentes."
            )

        tier1_count = sum(1 for i in ideas if "Tier 1" in i.tier)
        if tier1_count >= 3:
            recommendations.append(
                f"Hay {tier1_count} ideas excepcionales. Considerar presentar las 3 mejores al cliente."
            )
        elif tier1_count == 0:
            recommendations.append(
                "No hay ideas Tier 1. Considerar iterar sobre las ideas Tier 2 para mejorarlas."
            )

        return recommendations


# =============================================================================
# Singleton Access
# =============================================================================

_ideas_service: IdeasService | None = None


def get_ideas_service() -> IdeasService:
    """Get singleton ideas service."""
    global _ideas_service
    if _ideas_service is None:
        _ideas_service = IdeasService()
    return _ideas_service
