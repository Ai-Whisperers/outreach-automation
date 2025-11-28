"""
Batch Video Agent

Orchestrates automated Veo 3.1 video generation for all campaign ideas
with Nestlé branding.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from ..logging_config import get_logger
from .brand_context import get_brand_context
from .file_operations import get_file_service
from .video_service import get_video_service
from .ai_client import get_ai_manager

logger = get_logger("batch_video_agent")


@dataclass
class VideoGenerationResult:
    """Result of video generation for a single idea."""
    idea_number: int
    idea_title: str
    prompt_generated: bool
    video_generated: bool
    prompt_path: str | None = None
    video_path: str | None = None
    error: str | None = None


@dataclass
class BatchVideoReport:
    """Summary report of batch video generation."""
    project_id: str
    total_ideas: int
    prompts_generated: int
    videos_generated: int
    total_cost_estimate: float
    results: list[VideoGenerationResult]
    errors: list[str]


class BatchVideoAgent:
    """
    Automated agent for generating Veo 3.1 videos for all campaign ideas.
    Includes Nestlé branding and Paraguay cultural elements.
    """
    
    # Cost per 6-second video (estimated)
    COST_PER_VIDEO = 0.20  # $0.20 USD
    
    def __init__(self, parallel_limit: int = 3):
        """
        Initialize batch video agent.
        
        Args:
            parallel_limit: Maximum number of concurrent video generations
        """
        self.files = get_file_service()
        self.video_service = get_video_service()
        self.ai = get_ai_manager()
        self.brand = get_brand_context("paraguay")
        self.parallel_limit = parallel_limit
        self.semaphore = asyncio.Semaphore(parallel_limit)
    
    async def generate_all_videos(
        self,
        project_id: str,
        dry_run: bool = False,
        generate_videos: bool = True
    ) -\u003e BatchVideoReport:
        """
        Generate Veo 3.1 videos for all campaign ideas.
        
        Args:
            project_id: Project identifier
            dry_run: If True, only estimate cost without generating
            generate_videos: If False, only generate prompts
            
        Returns:
            Batch video generation report
        """
        logger.info(f"Starting batch video generation for: {project_id}")
        logger.info(f"Dry run: {dry_run}, Generate videos: {generate_videos}")
        
        # Get all ideas
        idea_files = self.files.get_idea_files(project_id)
        total_ideas = len(idea_files)
        
        logger.info(f"Found {total_ideas} campaign ideas")
        
        # Estimate cost
        estimated_cost = total_ideas * self.COST_PER_VIDEO if generate_videos else 0
        logger.info(f"Estimated cost: ${estimated_cost:.2f} USD")
        
        if dry_run:
            logger.info("Dry run mode - no generation will occur")
            return BatchVideoReport(
                project_id=project_id,
                total_ideas=total_ideas,
                prompts_generated=0,
                videos_generated=0,
                total_cost_estimate=estimated_cost,
                results=[],
                errors=[]
            )
        
        # Generate prompts and videos
        results = []
        errors = []
        
        # Process ideas in parallel
        tasks = [
            self._process_single_idea(project_id, idea_file, generate_videos)
            for idea_file in idea_files
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Separate successful results from errors
        successful_results = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            else:
                successful_results.append(result)
        
        # Count successes
        prompts_generated = sum(1 for r in successful_results if r.prompt_generated)
        videos_generated = sum(1 for r in successful_results if r.video_generated)
        
        logger.info(f"Batch complete: {prompts_generated} prompts, {videos_generated} videos")
        
        return BatchVideoReport(
            project_id=project_id,
            total_ideas=total_ideas,
            prompts_generated=prompts_generated,
            videos_generated=videos_generated,
            total_cost_estimate=videos_generated * self.COST_PER_VIDEO,
            results=successful_results,
            errors=errors
        )
    
    async def _process_single_idea(
        self,
        project_id: str,
        idea_file: str,
        generate_video: bool
    ) -\u003e VideoGenerationResult:
        """Process a single idea: generate prompt and optionally video."""
        async with self.semaphore:
            try:
                # Read idea content
                content = await self.files.read_file(project_id, idea_file)
                
                # Parse idea info
                title, number = self._parse_idea_info(content)
                
                logger.info(f"Processing idea {number}: {title}")
                
                # Generate branded prompt
                prompt_content = await self._generate_branded_prompt(title, content)
                
                # Save prompt
                prompt_filename = f"veo3/prompt-{number:03d}-{self._sanitize_filename(title)}.md"
                prompt_path = await self.files.write_file(project_id, prompt_filename, prompt_content)
                
                logger.info(f"Generated prompt for idea {number}")
                
                result = VideoGenerationResult(
                    idea_number=number,
                    idea_title=title,
                    prompt_generated=True,
                    video_generated=False,
                    prompt_path=str(prompt_path)
                )
                
                # Generate video if requested
                if generate_video:
                    video_path = await self._generate_single_video(
                        project_id,
                        prompt_content,
                        number,
                        title
                    )
                    
                    if video_path:
                        result.video_generated = True
                        result.video_path = str(video_path)
                        logger.info(f"Generated video for idea {number}")
                
                return result
                
            except Exception as e:
                logger.error(f"Failed to process {idea_file}: {e}")
                return VideoGenerationResult(
                    idea_number=0,
                    idea_title=idea_file,
                    prompt_generated=False,
                    video_generated=False,
                    error=str(e)
                )
    
    async def _generate_branded_prompt(self, title: str, idea_content: str) -\u003e str:
        """Generate a branded Veo 3.1 prompt with Nestlé visual identity."""
        
        system_prompt = f"""You are a Nestlé brand video expert specializing in Veo 3.1 prompts.
You create detailed, brand-compliant video prompts for Google DeepMind's Veo 3.1.

CRITICAL BRAND REQUIREMENTS (MUST INCLUDE):
{self.brand.get_veo_brand_instructions()}

VEO 3.1 BEST PRACTICES:
- Specific, cinematic visual descriptions
- Clear camera direction (shots, movements, angles)
- Lighting and color palette details
- Visual style and references
- Timing and pacing
- Scene transitions
- ALWAYS in ENGLISH for Veo 3.1 API"""

        user_prompt = f"""Generate a detailed Veo 3.1 prompt for this Nestlé Paraguay campaign:

CAMPAIGN IDEA:
{idea_content[:2000]}

{self.brand.get_market_description()}

Create a comprehensive document with:

## Contenido de Video (Veo 3.1)

### 1. Main Veo 3.1 Prompt (ENGLISH)
A complete, detailed 150-200 word prompt that MUST include:
- Nestlé brand colors ({self.brand.colors.primary}, {self.brand.colors.secondary})
- Nestlé logo placement ({self.brand.logo.placement[0]})
- Paraguay setting and cultural elements
- Visual style: {self.brand.visual_style.mood}
- Camera work and cinematography
- 6-second duration structure

### 2. Technical Specifications
- Aspect Ratio: 16:9
- Duration: 6 seconds
- Resolution: 1080p
- Visual Style: [describe]
- Color Palette: Nestlé brand colors
- Mood: {self.brand.visual_style.mood}

### 3. Scene Breakdown (6 seconds)
- 0-2s: [Opening scene]
- 2-4s: [Middle scene]
- 4-6s: [Closing with Nestlé logo]

### 4. Prompt Variations
Generate 3 alternative versions focusing on different aspects"""

        response = await self.ai.generate(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.7
        )
        
        # Validate brand compliance
        if not self.brand.is_brand_compliant(response):
            logger.warning(f"Generated prompt for '{title}' may not be fully brand compliant")
            validation = self.brand.validate_prompt(response)
            logger.debug(f"Brand validation: {validation}")
        
        return response
    
    async def _generate_single_video(
        self,
        project_id: str,
        prompt_content: str,
        idea_number: int,
        title: str
    ) -\u003e Path | None:
        """Generate a single video using Veo 3.1 API."""
        try:
            # Extract main prompt from content
            main_prompt = self._extract_main_prompt(prompt_content)
            
            if not main_prompt:
                logger.warning(f"No main prompt found for idea {idea_number}")
                return None
            
            # Call Veo 3.1 API (delegating to video service)
            # Note: This would need the video service to expose the API call
            # For now, we'll log that this would happen
            logger.info(f"Would call Veo 3.1 API for idea {idea_number}")
            logger.info(f"Prompt: {main_prompt[:100]}...")
            
            # TODO: Implement actual Veo 3.1 API call
            # video_bytes = await self.video_service._call_veo_api(...)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to generate video for idea {idea_number}: {e}")
            return None
    
    def _parse_idea_info(self, content: str) -\u003e tuple[str, int]:
        """Parse title and number from idea content."""
        title = "Untitled"
        number = 0
        
        lines = content.split('\n')
        for line in lines:
            if line.startswith('# Idea '):
                # Format: "# Idea 01: Title"
                parts = line.replace('# Idea ', '').split(':', 1)
                if len(parts) == 2:
                    try:
                        number = int(parts[0].strip())
                        title = parts[1].strip()
                    except ValueError:
                        pass
                break
        
        return title, number
    
    def _sanitize_filename(self, title: str) -\u003e str:
        """Sanitize title for use in filename."""
        # Remove special characters, keep only alphanumeric and spaces
        sanitized = ''.join(c if c.isalnum() or c.isspace() else '' for c in title)
        # Replace spaces with hyphens, lowercase, limit length
        return sanitized.lower().replace(' ', '-')[:30]
    
    def _extract_main_prompt(self, content: str) -\u003e str | None:
        """Extract the main Veo 3.1 prompt from markdown content."""
        lines = content.split('\n')
        in_prompt = False
        prompt = []
        
        for line in lines:
            if "Main Veo 3.1 Prompt" in line or "Prompt Principal" in line:
                in_prompt = True
                continue
            elif line.startswith("##") and in_prompt:
                break
            
            if in_prompt and line.strip() and not line.startswith('#'):
                prompt.append(line.strip())
        
        return " ".join(prompt) if prompt else None


# Singleton instance
_batch_video_agent: BatchVideoAgent | None = None


def get_batch_video_agent(parallel_limit: int = 3) -\u003e BatchVideoAgent:
    """Get singleton batch video agent instance."""
    global _batch_video_agent
    if _batch_video_agent is None:
        _batch_video_agent = BatchVideoAgent(parallel_limit=parallel_limit)
        logger.info(f"Initialized batch video agent (parallel_limit={parallel_limit})")
    return _batch_video_agent
