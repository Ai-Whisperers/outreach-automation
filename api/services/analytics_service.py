"""
Analytics Service for MAGA.

Provides intelligent analysis of research data, insights extraction,
and strategic recommendations for marketing campaigns.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..logging_config import get_logger
from .ai_client import AIClientManager as AIManager
from .file_operations import FileOperationsService

logger = get_logger("services.analytics")
settings = get_settings()


class AnalyticsService:
    """
    Service for generating analytics reports and insights from campaign data.
    """

    def __init__(
        self,
        ai_manager: AIManager | None = None,
        file_service: FileOperationsService | None = None
    ):
        """
        Initialize Analytics Service.

        Args:
            ai_manager: AI manager for LLM calls
            file_service: File operations service
        """
        self.ai = ai_manager
        self.files = file_service
        self.settings = settings

    async def generate_research_intelligence(
        self,
        project_id: str
    ) -> dict[str, Any]:
        """
        Generate comprehensive research intelligence report.

        Analyzes all research files to extract:
        - Market landscape overview
        - Consumer insights
        - Cultural context
        - Opportunity mapping

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with report content and metadata
        """
        logger.info(f"Generating research intelligence for project: {project_id}")

        # Load all research files
        research_content = await self._load_all_research(project_id)

        if not research_content:
            logger.warning(f"No research found for project: {project_id}")
            return {
                "status": "no_research",
                "message": "No research files found. Add research first."
            }

        # AI analysis prompt
        prompt = self._create_research_intelligence_prompt(research_content)

        # Generate insights
        response = await self.ai.generate_completion(
            prompt=prompt,
            temperature=0.3,  # Lower for analytical tasks
            max_tokens=4000
        )

        # Parse and structure the response
        intelligence = self._parse_research_intelligence(response)

        # Save report
        report_path = await self._save_report(
            project_id=project_id,
            report_name="RESEARCH-INTELLIGENCE-REPORT.md",
            content=intelligence["markdown"]
        )

        logger.info(f"Research intelligence report saved: {report_path}")

        return {
            "status": "success",
            "report_path": str(report_path),
            "insights_count": intelligence["insights_count"],
            "opportunities_count": intelligence["opportunities_count"],
            "metadata": intelligence["metadata"]
        }

    async def synthesize_strategic_insights(
        self,
        project_id: str
    ) -> dict[str, Any]:
        """
        Generate strategic insights synthesis.

        Creates executive summary connecting insights to strategy:
        - The big picture (3 bullets)
        - Key insights (top 5)
        - Strategic territories
        - Success factors

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with synthesis content
        """
        logger.info(f"Synthesizing strategic insights for: {project_id}")

        # Load research and brief
        research_content = await self._load_all_research(project_id)
        brief_content = await self._load_brief(project_id)

        # AI synthesis prompt
        prompt = self._create_strategic_synthesis_prompt(
            brief=brief_content,
            research=research_content
        )

        # Generate synthesis
        response = await self.ai.generate_completion(
            prompt=prompt,
            temperature=0.4,
            max_tokens=3000
        )

        # Parse response
        synthesis = self._parse_strategic_synthesis(response)

        # Save report
        report_path = await self._save_report(
            project_id=project_id,
            report_name="STRATEGIC-INSIGHTS-BRIEF.md",
            content=synthesis["markdown"]
        )

        logger.info(f"Strategic insights brief saved: {report_path}")

        return {
            "status": "success",
            "report_path": str(report_path),
            "key_insights_count": synthesis["insights_count"],
            "territories_count": synthesis["territories_count"]
        }

    async def map_insights_to_ideas(
        self,
        project_id: str
    ) -> dict[str, Any]:
        """
        Create mapping between insights and generated ideas.

        Shows:
        - Which insight inspired each idea
        - Insight coverage analysis
        - Insight strength ranking

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with mapping data
        """
        logger.info(f"Mapping insights to ideas for: {project_id}")

        # Load ideas
        ideas = await self._load_all_ideas(project_id)

        if not ideas:
            logger.warning(f"No ideas found for project: {project_id}")
            return {
                "status": "no_ideas",
                "message": "Generate ideas first before mapping."
            }

        # Load research intelligence (contains extracted insights)
        intelligence_path = self.files.get_project_path(project_id) / "analytics" / "RESEARCH-INTELLIGENCE-REPORT.md"

        if not intelligence_path.exists():
            # Generate research intelligence first
            await self.generate_research_intelligence(project_id)

        # AI mapping prompt
        prompt = self._create_insights_mapping_prompt(ideas)

        # Generate mapping
        response = await self.ai.generate_completion(
            prompt=prompt,
            temperature=0.3,
            max_tokens=3000
        )

        # Parse mapping
        mapping = self._parse_insights_mapping(response)

        # Save report
        report_path = await self._save_report(
            project_id=project_id,
            report_name="INSIGHTS-IDEAS-MAPPING.md",
            content=mapping["markdown"]
        )

        logger.info(f"Insights-to-ideas mapping saved: {report_path}")

        return {
            "status": "success",
            "report_path": str(report_path),
            "ideas_mapped": mapping["ideas_count"],
            "insights_used": mapping["insights_count"],
            "coverage_score": mapping["coverage_score"]
        }

    async def analyze_competitors(
        self,
        project_id: str
    ) -> dict[str, Any]:
        """
        Generate Competitive Intelligence Dashboard.

        Analyzes competitor data to create:
        - Competitor landscape map
        - Campaign analysis
        - Strengths & weaknesses
        - Strategic recommendations

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with competitive analysis
        """
        logger.info(f"Analyzing competitors for: {project_id}")

        # Load research content
        research_content = await self._load_all_research(project_id)
        brief_content = await self._load_brief(project_id)

        if not research_content:
            return {
                "status": "no_research",
                "message": "No research found. Add competitor research first."
            }

        # AI competitive analysis prompt
        prompt = self._create_competitive_analysis_prompt(
            brief=brief_content,
            research=research_content
        )

        # Generate analysis
        response = await self.ai.generate_completion(
            prompt=prompt,
            temperature=0.3,
            max_tokens=4000
        )

        # Parse response
        analysis = self._parse_competitive_analysis(response)

        # Save report
        report_path = await self._save_report(
            project_id=project_id,
            report_name="COMPETITIVE-INTELLIGENCE.md",
            content=analysis["markdown"]
        )

        logger.info(f"Competitive intelligence saved: {report_path}")

        return {
            "status": "success",
            "report_path": str(report_path),
            "competitors_analyzed": analysis["competitors_count"],
            "opportunities_identified": analysis["opportunities_count"],
            "metadata": analysis["metadata"]
        }

    async def identify_trends(
        self,
        project_id: str
    ) -> dict[str, Any]:
        """
        Generate Trend Analysis Report.

        Identifies and analyzes trends:
        - Macro trends (society-level)
        - Industry trends (category evolution)
        - Micro trends (emerging behaviors)
        - Trend implications for brand

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with trend analysis
        """
        logger.info(f"Identifying trends for: {project_id}")

        # Load research
        research_content = await self._load_all_research(project_id)
        brief_content = await self._load_brief(project_id)

        if not research_content:
            return {
                "status": "no_research",
                "message": "No research found. Add trend research first."
            }

        # AI trend analysis prompt
        prompt = self._create_trend_analysis_prompt(
            brief=brief_content,
            research=research_content
        )

        # Generate analysis
        response = await self.ai.generate_completion(
            prompt=prompt,
            temperature=0.4,
            max_tokens=4000
        )

        # Parse response
        trends = self._parse_trend_analysis(response)

        # Save report
        report_path = await self._save_report(
            project_id=project_id,
            report_name="TREND-ANALYSIS-REPORT.md",
            content=trends["markdown"]
        )

        logger.info(f"Trend analysis saved: {report_path}")

        return {
            "status": "success",
            "report_path": str(report_path),
            "trends_identified": trends["trends_count"],
            "high_priority_trends": trends["high_priority_count"],
            "metadata": trends["metadata"]
        }

    async def assess_research_quality(
        self,
        project_id: str
    ) -> dict[str, Any]:
        """
        Generate Research Quality Dashboard.

        Assesses research completeness and quality:
        - Coverage analysis by category
        - Source quality ratings
        - Gap identification
        - Recommendations for improvement

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with quality assessment
        """
        logger.info(f"Assessing research quality for: {project_id}")

        # Load all research
        research_content = await self._load_all_research(project_id)
        brief_content = await self._load_brief(project_id)

        # Count research files by category
        project_path = self.files.get_project_path(project_id)
        research_stats = await self._analyze_research_files(project_path)

        if not research_content:
            return {
                "status": "no_research",
                "message": "No research found to assess.",
                "stats": research_stats
            }

        # AI quality assessment prompt
        prompt = self._create_quality_assessment_prompt(
            brief=brief_content,
            research=research_content,
            stats=research_stats
        )

        # Generate assessment
        response = await self.ai.generate_completion(
            prompt=prompt,
            temperature=0.3,
            max_tokens=3000
        )

        # Parse response
        assessment = self._parse_quality_assessment(response, research_stats)

        # Save report
        report_path = await self._save_report(
            project_id=project_id,
            report_name="RESEARCH-QUALITY-DASHBOARD.md",
            content=assessment["markdown"]
        )

        logger.info(f"Research quality dashboard saved: {report_path}")

        return {
            "status": "success",
            "report_path": str(report_path),
            "total_sources": research_stats["total_files"],
            "quality_score": assessment["quality_score"],
            "gaps_identified": assessment["gaps_count"],
            "metadata": assessment["metadata"]
        }

    async def create_audience_personas(
        self,
        project_id: str
    ) -> dict[str, Any]:
        """
        Generate Audience Deep Dive Report.

        Creates detailed audience personas:
        - Demographic profiles
        - Psychographic profiles
        - 3-5 detailed personas with names & stories
        - Customer journey mapping
        - Segmentation strategy

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with audience personas
        """
        logger.info(f"Creating audience personas for: {project_id}")

        # Load research and brief
        research_content = await self._load_all_research(project_id)
        brief_content = await self._load_brief(project_id)

        if not research_content:
            return {
                "status": "no_research",
                "message": "No research found. Add audience research first."
            }

        # AI persona creation prompt
        prompt = self._create_audience_personas_prompt(
            brief=brief_content,
            research=research_content
        )

        # Generate personas
        response = await self.ai.generate_completion(
            prompt=prompt,
            temperature=0.5,
            max_tokens=4000
        )

        # Parse response
        personas = self._parse_audience_personas(response)

        # Save report
        report_path = await self._save_report(
            project_id=project_id,
            report_name="AUDIENCE-INSIGHTS-REPORT.md",
            content=personas["markdown"]
        )

        logger.info(f"Audience insights report saved: {report_path}")

        return {
            "status": "success",
            "report_path": str(report_path),
            "personas_created": personas["personas_count"],
            "segments_identified": personas["segments_count"],
            "metadata": personas["metadata"]
        }

    async def generate_content_strategy(
        self,
        project_id: str
    ) -> dict[str, Any]:
        """
        Generate Content Strategy Framework.

        Creates content strategy:
        - 3-5 content pillars based on audience interests
        - Channel strategy (which content on which platform)
        - Content calendar template
        - Engagement tactics & CTAs

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with content strategy
        """
        logger.info(f"Generating content strategy for: {project_id}")

        # Load research, brief, and personas
        research_content = await self._load_all_research(project_id)
        brief_content = await self._load_brief(project_id)

        # Check if personas exist
        personas_path = self.files.get_project_path(project_id) / "analytics" / "AUDIENCE-INSIGHTS-REPORT.md"
        if not personas_path.exists():
            # Generate personas first
            await self.create_audience_personas(project_id)

        # AI content strategy prompt
        prompt = self._create_content_strategy_prompt(
            brief=brief_content,
            research=research_content
        )

        # Generate strategy
        response = await self.ai.generate_completion(
            prompt=prompt,
            temperature=0.4,
            max_tokens=4000
        )

        # Parse response
        strategy = self._parse_content_strategy(response)

        # Save report
        report_path = await self._save_report(
            project_id=project_id,
            report_name="CONTENT-STRATEGY-FRAMEWORK.md",
            content=strategy["markdown"]
        )

        logger.info(f"Content strategy framework saved: {report_path}")

        return {
            "status": "success",
            "report_path": str(report_path),
            "content_pillars": strategy["pillars_count"],
            "channels_covered": strategy["channels_count"],
            "metadata": strategy["metadata"]
        }

    async def validate_cultural_sensitivity(
        self,
        project_id: str
    ) -> dict[str, Any]:
        """
        Generate Cultural Sensitivity Report.

        Validates cultural appropriateness:
        - Cultural codes & values
        - Language nuances (Spanish + Guaraní)
        - Visual guidelines (colors, imagery)
        - Campaign validation checklist

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with cultural validation
        """
        logger.info(f"Validating cultural sensitivity for: {project_id}")

        # Load research and brief
        research_content = await self._load_all_research(project_id)
        brief_content = await self._load_brief(project_id)

        # Load ideas for validation
        ideas = await self._load_all_ideas(project_id)

        # AI cultural validation prompt
        prompt = self._create_cultural_validation_prompt(
            brief=brief_content,
            research=research_content,
            ideas=ideas
        )

        # Generate validation
        response = await self.ai.generate_completion(
            prompt=prompt,
            temperature=0.3,
            max_tokens=4000
        )

        # Parse response
        validation = self._parse_cultural_validation(response)

        # Save report
        report_path = await self._save_report(
            project_id=project_id,
            report_name="CULTURAL-SENSITIVITY-ANALYSIS.md",
            content=validation["markdown"]
        )

        logger.info(f"Cultural sensitivity analysis saved: {report_path}")

        return {
            "status": "success",
            "report_path": str(report_path),
            "cultural_codes_identified": validation["codes_count"],
            "validation_score": validation["validation_score"],
            "metadata": validation["metadata"]
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _load_all_research(self, project_id: str) -> str:
        """Load and concatenate all research files."""
        project_path = self.files.get_project_path(project_id)
        research_dirs = list(project_path.glob("investigacion-*"))

        all_research = []

        for research_dir in research_dirs:
            if research_dir.is_dir():
                for research_file in research_dir.glob("*.md"):
                    try:
                        content = research_file.read_text(encoding="utf-8")
                        all_research.append(f"## {research_file.stem}\n\n{content}")
                    except Exception as e:
                        logger.warning(f"Failed to read {research_file}: {e}")

        return "\n\n---\n\n".join(all_research)

    async def _load_brief(self, project_id: str) -> str:
        """Load project brief."""
        try:
            return await self.files.read_file(project_id, "brief-original.md")
        except Exception as e:
            logger.warning(f"Failed to load brief: {e}")
            return ""

    async def _load_all_ideas(self, project_id: str) -> list[dict[str, Any]]:
        """Load all generated ideas."""
        project_path = self.files.get_project_path(project_id)
        ideas_dir = project_path / "ideas"

        if not ideas_dir.exists():
            return []

        ideas = []
        for idea_file in sorted(ideas_dir.glob("idea-*.md")):
            try:
                content = idea_file.read_text(encoding="utf-8")
                ideas.append({
                    "number": idea_file.stem.split("-")[1],
                    "filename": idea_file.name,
                    "content": content
                })
            except Exception as e:
                logger.warning(f"Failed to read {idea_file}: {e}")

        return ideas

    async def _save_report(
        self,
        project_id: str,
        report_name: str,
        content: str
    ) -> Path:
        """Save analytics report to project."""
        project_path = self.files.get_project_path(project_id)
        analytics_dir = project_path / "analytics"
        analytics_dir.mkdir(exist_ok=True)

        report_path = analytics_dir / report_name
        report_path.write_text(content, encoding="utf-8")

        return report_path

    async def _analyze_research_files(self, project_path: Path) -> dict[str, Any]:
        """Analyze research files and categorize them."""
        research_dirs = list(project_path.glob("investigacion-*"))

        stats = {
            "total_files": 0,
            "by_category": {},
            "file_list": []
        }

        for research_dir in research_dirs:
            if research_dir.is_dir():
                for research_file in research_dir.glob("*.md"):
                    stats["total_files"] += 1
                    stats["file_list"].append(research_file.name)

                    # Categorize by filename keywords
                    filename_lower = research_file.stem.lower()
                    if any(word in filename_lower for word in ["competitor", "competition", "rival"]):
                        category = "competitor_analysis"
                    elif any(word in filename_lower for word in ["trend", "trending", "emerging"]):
                        category = "trends"
                    elif any(word in filename_lower for word in ["market", "industry", "sector"]):
                        category = "market_analysis"
                    elif any(word in filename_lower for word in ["consumer", "customer", "audience"]):
                        category = "consumer_research"
                    elif any(word in filename_lower for word in ["cultural", "culture", "local"]):
                        category = "cultural_insights"
                    else:
                        category = "general"

                    stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

        return stats

    # =========================================================================
    # AI Prompt Creation
    # =========================================================================

    def _create_research_intelligence_prompt(self, research: str) -> str:
        """Create prompt for research intelligence extraction."""
        return f"""Analyze the following research documents and create a comprehensive Research Intelligence Report.

Extract and organize:

1. **Market Landscape Overview** (3-5 key points)
   - Industry trends
   - Market dynamics
   - Key players

2. **Consumer Insights** (5-7 insights)
   - Behavioral patterns
   - Pain points & needs
   - Decision-making factors
   - Purchase triggers

3. **Cultural Context** (3-5 points)
   - Local customs & traditions
   - Language nuances
   - Social values
   - Regional differences

4. **Opportunity Map** (5-7 opportunities)
   - White space identification
   - Unmet needs
   - Emerging trends
   - Innovation opportunities

For each insight and opportunity:
- State it clearly in one sentence
- Provide supporting evidence from research
- Explain strategic implications
- Rate importance (High/Medium/Low)

Format as markdown with clear sections and bullet points.

Research Documents:
{research[:15000]}

Generate the report now:"""

    def _create_strategic_synthesis_prompt(
        self,
        brief: str,
        research: str
    ) -> str:
        """Create prompt for strategic insights synthesis."""
        return f"""Create an executive Strategic Insights Brief that connects research to strategy.

Based on the brief and research, provide:

1. **The Big Picture** (exactly 3 bullets)
   - Market context in one sentence
   - Consumer truth in one sentence
   - Strategic opportunity in one sentence

2. **Key Insights** (exactly 5 insights, ranked by importance)
   For each:
   - The insight (one clear sentence)
   - Why it matters (implications)
   - What to do about it (recommended actions)

3. **Strategic Territories** (3-5 potential campaign directions)
   - Based on insights
   - Aligned with trends
   - Differentiated from competition
   - Each with a catchy name and one-paragraph description

4. **Success Factors** (3-5 points)
   - What will make campaigns work
   - What to avoid
   - Critical success criteria

Format as executive-friendly markdown. Be concise and actionable.

Brief:
{brief[:5000]}

Research Summary:
{research[:10000]}

Generate the strategic brief now:"""

    def _create_insights_mapping_prompt(self, ideas: list[dict]) -> str:
        """Create prompt for insights-to-ideas mapping."""
        ideas_summary = "\n\n".join([
            f"**Idea {idea['number']}:**\n{idea['content'][:500]}"
            for idea in ideas[:25]
        ])

        return f"""Analyze these campaign ideas and create an Insights-to-Ideas Mapping.

For each idea, identify:
1. The core consumer insight it's based on
2. How the insight is expressed in the campaign
3. Strength of the insight-idea connection (Strong/Medium/Weak)

Then provide:
- **Insight Coverage Analysis**: Which insights are well-covered, which are underutilized
- **Insight Strength Ranking**: Most powerful insights across all ideas
- **Gaps**: Insights that could be explored more

Format as markdown with clear sections.

Campaign Ideas:
{ideas_summary}

Generate the mapping now:"""

    def _create_competitive_analysis_prompt(self, brief: str, research: str) -> str:
        """Create prompt for competitive analysis."""
        return f"""Analyze competitor data and create a Competitive Intelligence Dashboard.

Based on the brief and research, provide:

1. **Competitor Landscape** (3-5 key competitors)
   For each competitor:
   - Name and positioning
   - Market share/presence
   - Key strengths
   - Notable weaknesses

2. **Campaign Analysis** (recent competitor campaigns)
   - Campaign themes and messaging
   - Creative territories explored
   - Channel mix and tactics
   - Estimated effectiveness

3. **Positioning Map**
   - Map competitors on 2 axes (e.g., Traditional ← → Innovative, Functional ← → Emotional)
   - Identify white space opportunities
   - Show where our brand should position

4. **Strategic Recommendations**
   - How to differentiate
   - Where to compete directly
   - Where to avoid
   - Opportunities to exploit

Format as markdown with clear sections.

Brief:
{brief[:5000]}

Research:
{research[:12000]}

Generate the competitive intelligence now:"""

    def _create_trend_analysis_prompt(self, brief: str, research: str) -> str:
        """Create prompt for trend analysis."""
        return f"""Identify and analyze relevant trends for this campaign.

Based on the brief and research, provide:

1. **Macro Trends** (3-5 society-level trends)
   For each trend:
   - Trend name and description
   - Velocity (how fast it's growing): 1-10
   - Relevance (fit with brand): 1-10
   - Longevity (fad vs lasting): 1-10
   - Strategic implications

2. **Industry Trends** (3-5 category-specific trends)
   - Category evolution patterns
   - Innovation directions
   - Consumer preference shifts
   - Competitive dynamics

3. **Micro Trends** (2-4 emerging behaviors)
   - Early signals worth watching
   - Niche movements
   - Potential future trends

4. **Trend Implications**
   - Opportunities for the brand
   - Threats to address
   - Campaign ideas aligned to trends
   - Recommended actions

Prioritize trends by: Velocity × Relevance × Longevity

Format as markdown with clear sections and scores.

Brief:
{brief[:5000]}

Research:
{research[:12000]}

Generate the trend analysis now:"""

    def _create_quality_assessment_prompt(
        self,
        brief: str,
        research: str,
        stats: dict
    ) -> str:
        """Create prompt for research quality assessment."""
        return f"""Assess the quality and completeness of research for this campaign.

Current Research Stats:
- Total sources: {stats['total_files']}
- By category: {stats.get('by_category', {})}

Based on the brief requirements and current research, provide:

1. **Coverage Analysis**
   For each category (Market, Consumer, Competitor, Cultural, Trends):
   - Current coverage: Excellent/Good/Fair/Poor
   - Number of sources
   - Key gaps identified

2. **Source Quality**
   - Credibility assessment
   - Recency check (are sources current?)
   - Relevance to brief
   - Depth of insights

3. **Gap Identification**
   - What's missing?
   - Critical gaps (must-have)
   - Nice-to-have additions
   - Prioritized recommendations

4. **Research Recommendations**
   - Specific sources to add (URLs or types)
   - Primary research needs
   - Expert interviews suggested
   - Next steps

5. **Overall Quality Score** (1-10)
   - Justify the score
   - What would make it a 10?

Format as markdown with clear sections and actionable recommendations.

Brief:
{brief[:5000]}

1. **Market Landscape Overview** (3-5 key points)
   - Industry trends
   - Market dynamics
   - Key players

2. **Consumer Insights** (5-7 insights)
   - Behavioral patterns
   - Pain points & needs
   - Decision-making factors
   - Purchase triggers

3. **Cultural Context** (3-5 points)
   - Local customs & traditions
   - Language nuances
   - Social values
   - Regional differences

4. **Opportunity Map** (5-7 opportunities)
   - White space identification
   - Unmet needs
   - Emerging trends
   - Innovation opportunities

For each insight and opportunity:
- State it clearly in one sentence
- Provide supporting evidence from research
- Explain strategic implications
- Rate importance (High/Medium/Low)

Format as markdown with clear sections and bullet points.

Research Documents:
{research[:15000]}  # Limit to avoid token overflow

Generate the report now:"""

    # =========================================================================
    # Response Parsing
    # =========================================================================

    def _parse_research_intelligence(self, response: str) -> dict[str, Any]:
        """Parse AI response for research intelligence."""
        # Count insights and opportunities
        insights_count = response.count("**Consumer Insights**")
        opportunities_count = response.count("**Opportunity Map**")

        return {
            "markdown": response,
            "insights_count": max(5, insights_count * 5),  # Estimate
            "opportunities_count": max(5, opportunities_count * 5),
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "ai_model": "gpt-4o-mini"
            }
        }

    def _parse_strategic_synthesis(self, response: str) -> dict[str, Any]:
        """Parse AI response for strategic synthesis."""
        insights_count = 5  # We asked for exactly 5
        territories_count = response.count("**Strategic Territories**")

        return {
            "markdown": response,
            "insights_count": insights_count,
            "territories_count": max(3, territories_count * 3),
            "metadata": {
                "generated_at": datetime.utcnow().isoformat()
            }
        }

    def _parse_insights_mapping(self, response: str) -> dict[str, Any]:
        """Parse AI response for insights mapping."""
        ideas_count = response.count("**Idea")
        insights_count = response.count("Insight:")

        # Simple coverage score based on how many ideas have insights mapped
        coverage_score = min(100, (insights_count / max(1, ideas_count)) * 100)

        return {
            "markdown": response,
            "ideas_count": ideas_count,
            "insights_count": insights_count,
            "coverage_score": round(coverage_score, 1),
            "metadata": {
                "generated_at": datetime.utcnow().isoformat()
            }
        }
