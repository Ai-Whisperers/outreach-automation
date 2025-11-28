"""
Synthesis Service

Synthesizes research into actionable insights and quick references.
"""


from ..logging_config import get_logger
from ..models import KeyInsight, MarketSnapshot, QuickReference, SynthesizeResponse, Target30Seconds
from .ai_client import get_ai_manager, get_prompt_loader
from .file_operations import get_file_service
from .research_service import get_research_service
from .template_renderer import get_template_renderer

logger = get_logger("synthesis_service")


# =============================================================================
# Synthesis Service
# =============================================================================

class SynthesisService:
    """
    Service for synthesizing research into actionable outputs.
    """

    def __init__(self):
        self.ai = get_ai_manager()
        self.prompts = get_prompt_loader()
        self.files = get_file_service()
        self.renderer = get_template_renderer()
        self.research = get_research_service()

    async def synthesize(
        self,
        project_id: str,
        include_quick_reference: bool = True,
        include_insights: bool = True,
        include_dos_donts: bool = True
    ) -> SynthesizeResponse:
        """
        Synthesize all research into actionable outputs.

        Args:
            project_id: Project identifier
            include_quick_reference: Generate quick reference
            include_insights: Generate insights
            include_dos_donts: Generate do's and don'ts

        Returns:
            Synthesis response with generated files
        """
        logger.info(f"Synthesizing research for project: {project_id}")

        # Get all research content
        research_content = await self.research.get_all_research(project_id)

        if not research_content:
            logger.warning(f"No research found for project: {project_id}")
            return SynthesizeResponse(
                project_id=project_id,
                quick_reference=None,
                files_created=[]
            )

        files_created = []
        quick_reference = None

        # Generate quick reference
        if include_quick_reference:
            quick_reference = await self._generate_quick_reference(research_content)

            # Render and save
            metadata = self.files.get_project_metadata(project_id)
            rendered = self.renderer.render_quick_reference(
                project_name=metadata.get("name", "Campaign"),
                challenge=quick_reference.challenge_one_liner,
                market_snapshot={
                    "size": quick_reference.market_snapshot.size,
                    "growth": quick_reference.market_snapshot.growth,
                    "brand_share": quick_reference.market_snapshot.brand_share,
                    "main_competitor": quick_reference.market_snapshot.main_competitor
                },
                target={
                    "who": quick_reference.target_30_seconds.who,
                    "age": quick_reference.target_30_seconds.age,
                    "motivation": quick_reference.target_30_seconds.motivation,
                    "barrier": quick_reference.target_30_seconds.barrier,
                    "media": quick_reference.target_30_seconds.media
                },
                insights=[
                    {
                        "problem": i.problem,
                        "reality": i.reality,
                        "opportunity": i.opportunity
                    }
                    for i in quick_reference.key_insights
                ],
                dos=quick_reference.dos,
                donts=quick_reference.donts,
                brainstorm_questions=quick_reference.brainstorm_questions
            )

            await self.files.write_file(project_id, "quick-reference.md", rendered)
            files_created.append("quick-reference.md")

        # Update project status
        self.files.update_project_metadata(project_id, {
            "status": "synthesized",
            "synthesis_complete": True
        })

        logger.info(f"Synthesis complete for project: {project_id}")

        return SynthesizeResponse(
            project_id=project_id,
            quick_reference=quick_reference,
            files_created=files_created
        )

    async def _generate_quick_reference(self, research_content: str) -> QuickReference:
        """
        Generate quick reference from research.

        Args:
            research_content: Combined research content

        Returns:
            Quick reference data
        """
        logger.debug("Generating quick reference")

        system, user = self.prompts.format(
            "synthesis", "quick_reference",
            research_content=research_content
        )

        response = await self.ai.generate_json(
            prompt=user,
            system=system,
            temperature=0.5
        )

        # Parse market snapshot
        market = response.get("market_snapshot", {})
        market_snapshot = MarketSnapshot(
            size=market.get("size", "N/A"),
            growth=market.get("growth", "N/A"),
            brand_share=market.get("brand_share", "N/A"),
            main_competitor=market.get("main_competitor", "N/A")
        )

        # Parse target
        target = response.get("target_30_seconds", {})
        target_30 = Target30Seconds(
            who=target.get("who", "N/A"),
            age=target.get("age", "N/A"),
            motivation=target.get("motivation", "N/A"),
            barrier=target.get("barrier", "N/A"),
            media=target.get("media", "N/A")
        )

        # Parse insights
        insights = []
        for i in response.get("key_insights", []):
            insights.append(KeyInsight(
                problem=i.get("problem", ""),
                reality=i.get("reality", ""),
                opportunity=i.get("opportunity", "")
            ))

        return QuickReference(
            challenge_one_liner=response.get("challenge_one_liner", ""),
            market_snapshot=market_snapshot,
            target_30_seconds=target_30,
            key_insights=insights,
            dos=response.get("dos", []),
            donts=response.get("donts", []),
            brainstorm_questions=response.get("brainstorm_questions", [])
        )

    async def generate_insights(self, project_id: str) -> list[KeyInsight]:
        """
        Generate additional insights from research.

        Args:
            project_id: Project identifier

        Returns:
            List of key insights
        """
        logger.debug(f"Generating insights for project: {project_id}")

        research_content = await self.research.get_all_research(project_id)

        system, user = self.prompts.format(
            "synthesis", "insights",
            research_content=research_content
        )

        response = await self.ai.generate_json(
            prompt=user,
            system=system,
            temperature=0.6
        )

        insights = []
        for i in response.get("insights", []):
            insights.append(KeyInsight(
                problem=i.get("problem", ""),
                reality=i.get("reality", ""),
                opportunity=i.get("opportunity", "")
            ))

        return insights

    async def generate_dos_donts(self, project_id: str) -> tuple[list[str], list[str]]:
        """
        Generate do's and don'ts from research.

        Args:
            project_id: Project identifier

        Returns:
            Tuple of (dos, donts) lists
        """
        logger.debug(f"Generating do's and don'ts for project: {project_id}")

        research_content = await self.research.get_all_research(project_id)

        system, user = self.prompts.format(
            "synthesis", "dos_donts",
            research_content=research_content
        )

        response = await self.ai.generate_json(
            prompt=user,
            system=system,
            temperature=0.5
        )

        return response.get("dos", []), response.get("donts", [])


# =============================================================================
# Singleton Access
# =============================================================================

_synthesis_service: SynthesisService | None = None


def get_synthesis_service() -> SynthesisService:
    """Get singleton synthesis service."""
    global _synthesis_service
    if _synthesis_service is None:
        _synthesis_service = SynthesisService()
    return _synthesis_service
