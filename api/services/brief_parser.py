"""
Brief Parser Service

Parses campaign briefs and extracts structured information using AI.
Refactored to use Instructor for robust Pydantic validation.
"""

import instructor
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from ..config import get_settings
from ..logging_config import get_logger
from ..models import (
    BriefAnalysis,
    BriefParseResponse,
    BriefRequirements,
    CreativeDirection,
    TargetAudience,
)
from .ai_client import get_prompt_loader
from .file_operations import get_file_service

logger = get_logger("brief_parser")
settings = get_settings()

# =============================================================================
# Helper Models
# =============================================================================
from pydantic import BaseModel


class DirectionsResponse(BaseModel):
    """Wrapper for list of creative directions."""
    directions: list[CreativeDirection]

# =============================================================================
# Brief Parser Service
# =============================================================================

class BriefParserService:
    """
    Service for parsing campaign briefs and extracting insights.
    """

    def __init__(self):
        self.prompts = get_prompt_loader()
        self.files = get_file_service()

        # Initialize Instructor client
        if settings.anthropic_api_key:
            self.client = instructor.from_anthropic(
                AsyncAnthropic(api_key=settings.anthropic_api_key)
            )
            self.model = "claude-3-sonnet-20240229"
        else:
            self.client = instructor.from_openai(
                AsyncOpenAI(api_key=settings.openai_api_key)
            )
            self.model = "gpt-4-turbo-preview"

    async def parse_brief(self, project_id: str, brief_content: str) -> BriefParseResponse:
        """
        Parse a brief and extract all structured information.

        Args:
            project_id: Project identifier
            brief_content: Raw brief content in markdown

        Returns:
            Complete parsed brief response
        """
        logger.info(f"Parsing brief for project: {project_id}")

        # Save original brief
        await self.files.write_file(project_id, "brief-original.md", brief_content)

        # Extract all components
        # Note: We could run these in parallel with asyncio.gather, but sequential is safer for now
        # to avoid rate limits if using a small tier.
        challenge = await self._extract_challenge(brief_content)
        target = await self._extract_target(brief_content)
        directions = await self._extract_directions(brief_content, challenge, target)
        requirements = await self._extract_requirements(brief_content)

        # Update project metadata
        self.files.update_project_metadata(project_id, {
            "status": "brief_parsed",
            "brief_parsed": True
        })

        logger.info(f"Brief parsed successfully for project: {project_id}")

        return BriefParseResponse(
            project_id=project_id,
            challenge=challenge,
            target=target,
            directions=directions,
            requirements=requirements
        )

    async def _extract_challenge(self, brief_content: str) -> BriefAnalysis:
        """Extract the core challenge from brief."""
        logger.debug("Extracting challenge from brief")

        system, user = self.prompts.format(
            "brief", "challenge",
            brief_content=brief_content
        )

        return await self.client.chat.completions.create(
            model=self.model,
            response_model=BriefAnalysis,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0.0,
            max_tokens=4096
        )

    async def _extract_target(self, brief_content: str) -> TargetAudience:
        """Extract target audience details from brief."""
        logger.debug("Extracting target audience from brief")

        system, user = self.prompts.format(
            "brief", "target",
            brief_content=brief_content
        )

        return await self.client.chat.completions.create(
            model=self.model,
            response_model=TargetAudience,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0.0,
            max_tokens=4096
        )

    async def _extract_directions(
        self,
        brief_content: str,
        challenge: BriefAnalysis,
        target: TargetAudience
    ) -> list[CreativeDirection]:
        """Generate creative direction suggestions."""
        logger.debug("Generating creative directions")

        system, user = self.prompts.format(
            "brief", "directions",
            brief_content=brief_content,
            challenge=challenge.main_challenge,
            target=target.primary
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            response_model=DirectionsResponse,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0.5, # Slightly creative
            max_tokens=4096
        )

        return response.directions

    async def _extract_requirements(self, brief_content: str) -> BriefRequirements:
        """Extract brand requirements and restrictions."""
        logger.debug("Extracting brand requirements")

        system, user = self.prompts.format(
            "brief", "requirements",
            brief_content=brief_content
        )

        return await self.client.chat.completions.create(
            model=self.model,
            response_model=BriefRequirements,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            temperature=0.0,
            max_tokens=4096
        )

    async def save_parsed_brief(self, project_id: str, parsed: BriefParseResponse):
        """
        Save parsed brief as structured markdown.

        Args:
            project_id: Project identifier
            parsed: Parsed brief response
        """
        from .template_renderer import get_template_renderer
        renderer = get_template_renderer()

        # Build content for brief template
        content = renderer.render_brief(
            client=self.files.get_project_metadata(project_id).get("client", ""),
            product="",  # Would need to extract from brief
            objective=parsed.challenge.main_challenge,
            target={
                "primary": parsed.target.primary,
                "secondary": parsed.target.secondary,
                "age_range": parsed.target.age_range,
                "gender": parsed.target.gender,
                "location": parsed.target.location
            },
            problem=parsed.challenge.context,
            mandatories=parsed.requirements.mandatories,
            budget="",  # Would extract from brief
            timing={},  # Would extract from brief
            formats=[],  # Would extract from brief
            kpis=[],  # Would extract from brief
            context=parsed.challenge.success_looks_like
        )

        await self.files.write_file(project_id, "brief-expanded.md", content)
        logger.debug(f"Saved expanded brief for project: {project_id}")


# =============================================================================
# Singleton Access
# =============================================================================

_brief_parser: BriefParserService | None = None


def get_brief_parser() -> BriefParserService:
    """Get singleton brief parser service."""
    global _brief_parser
    if _brief_parser is None:
        _brief_parser = BriefParserService()
    return _brief_parser
