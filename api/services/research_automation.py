"""
Research Automation Service

Systematically gathers data from the web for each research phase.
Automates the entire research pipeline for campaign generation.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from ..logging_config import get_logger
from ..models import ResearchSource
from .ai_client import get_ai_manager, get_prompt_loader
from .research_service import get_research_service
from .web_fetcher import get_web_fetcher
from .web_search import get_web_search_service

logger = get_logger("research_automation")


# =============================================================================
# Research Phase Configuration
# =============================================================================

RESEARCH_PHASES = {
    "01-mercado-general": {
        "name": "Market Analysis",
        "description": "General market size, trends, and industry overview",
        "query_templates": [
            "{industry} market {country} {year} statistics",
            "{industry} industry {country} market size growth",
            "{industry} market trends {country} {year}",
            "{industry} sector {country} analysis report",
            "{industry} consumption statistics {country}"
        ],
        "min_sources": 3,
        "priority": 1
    },
    "02-marca": {
        "name": "Brand Analysis",
        "description": "Brand history, positioning, portfolio, and campaigns",
        "query_templates": [
            "{brand} {country} history brand",
            "{brand} marketing campaigns {year}",
            "{brand} brand positioning strategy",
            "{brand} product portfolio {country}",
            "{brand} official site {country}"
        ],
        "min_sources": 3,
        "priority": 2
    },
    "03-competencia": {
        "name": "Competitive Analysis",
        "description": "Direct and indirect competitors, market share",
        "query_templates": [
            "{brand} competitors {country} market share",
            "{industry} brands {country} comparison",
            "{industry} top brands {country} {year}",
            "{brand} vs competitors analysis",
            "{industry} competitive landscape {country}"
        ],
        "min_sources": 3,
        "priority": 3
    },
    "04-consumidor": {
        "name": "Consumer Research",
        "description": "Demographics, psychographics, behavior, digital habits",
        "query_templates": [
            "{target_audience} {country} demographics statistics",
            "{target_audience} consumer behavior {country}",
            "{target_audience} digital habits {country} social media",
            "{target_audience} preferences {industry} {country}",
            "{target_audience} purchase decision {country}"
        ],
        "min_sources": 4,
        "priority": 4
    },
    "05-cultura-local": {
        "name": "Cultural Context",
        "description": "Local traditions, language, values, occasions",
        "query_templates": [
            "{country} culture traditions {industry}",
            "{country} local expressions language slang",
            "{country} consumer culture values",
            "{country} celebrations occasions {season}",
            "{country} cultural insights marketing"
        ],
        "min_sources": 3,
        "priority": 5
    },
    "06-estadisticas": {
        "name": "Statistics & Data",
        "description": "Key metrics, verified data points, rankings",
        "query_templates": [
            "{industry} {country} statistics {year} official",
            "{brand} market share {country} {year}",
            "{industry} consumption data {country}",
            "{country} {industry} economic indicators",
            "{industry} growth rate {country} {year}"
        ],
        "min_sources": 3,
        "priority": 6
    },
    "07-referencias": {
        "name": "Source Documentation",
        "description": "Compile and verify all sources used",
        "query_templates": [],  # Generated from collected sources
        "min_sources": 0,
        "priority": 7
    },
    "08-investigacion-creativa": {
        "name": "Creative Research",
        "description": "Award-winning campaigns, viral content, visual references",
        "query_templates": [
            "{industry} award winning campaigns Cannes Lions {year}",
            "{industry} viral marketing campaigns Latin America",
            "{country} viral content social media {year}",
            "{industry} creative advertising examples",
            "{brand} successful campaigns case study"
        ],
        "min_sources": 4,
        "priority": 8
    }
}


# =============================================================================
# Research Automation Service
# =============================================================================

class ResearchAutomationService:
    """
    Service for automating the entire research pipeline.
    Systematically gathers data for each research phase.
    """

    def __init__(self):
        self.search = get_web_search_service()
        self.fetcher = get_web_fetcher()
        self.research = get_research_service()
        self.ai = get_ai_manager()
        self.prompts = get_prompt_loader()

    async def run_full_research(
        self,
        project_id: str,
        brief_data: dict[str, Any],
        phases: list[str] | None = None,
        results_per_phase: int = 5
    ) -> dict[str, Any]:
        """
        Run complete research automation for a project.

        Args:
            project_id: Project identifier
            brief_data: Extracted brief information
            phases: Specific phases to run (default: all)
            results_per_phase: Number of search results per phase

        Returns:
            Research summary with all gathered data
        """
        logger.info(f"Starting automated research for project: {project_id}")

        # Determine which phases to run
        if phases is None:
            phases = list(RESEARCH_PHASES.keys())

        # Extract variables from brief
        variables = self._extract_brief_variables(brief_data)

        results = {
            "project_id": project_id,
            "started_at": datetime.utcnow().isoformat(),
            "phases_completed": [],
            "total_sources": 0,
            "files_created": [],
            "errors": []
        }

        # Run each phase
        for phase_id in sorted(phases, key=lambda x: RESEARCH_PHASES.get(x, {}).get("priority", 99)):
            if phase_id not in RESEARCH_PHASES:
                logger.warning(f"Unknown phase: {phase_id}")
                continue

            try:
                phase_result = await self._run_phase(
                    project_id,
                    phase_id,
                    variables,
                    results_per_phase
                )
                results["phases_completed"].append(phase_id)
                results["total_sources"] += phase_result.get("sources_added", 0)
                results["files_created"].extend(phase_result.get("files", []))

            except Exception as e:
                logger.error(f"Error in phase {phase_id}: {e}")
                results["errors"].append({
                    "phase": phase_id,
                    "error": str(e)
                })

        # Generate summary documents
        await self._generate_summary_documents(project_id, results)

        results["completed_at"] = datetime.utcnow().isoformat()
        logger.info(f"Research automation completed for project: {project_id}")

        return results

    async def _run_phase(
        self,
        project_id: str,
        phase_id: str,
        variables: dict[str, str],
        results_per_query: int
    ) -> dict[str, Any]:
        """
        Run a single research phase.

        Args:
            project_id: Project identifier
            phase_id: Phase identifier (e.g., "01-mercado-general")
            variables: Template variables from brief
            results_per_query: Number of results per query

        Returns:
            Phase results
        """
        phase_config = RESEARCH_PHASES[phase_id]
        logger.info(f"Running phase: {phase_id} - {phase_config['name']}")

        # Generate search queries
        queries = self._generate_queries(
            phase_config["query_templates"],
            variables
        )

        if not queries:
            logger.info(f"No queries for phase {phase_id}")
            return {"sources_added": 0, "files": []}

        # Perform searches
        search_results = []
        for query in queries:
            results = await self.search.search(query, results_per_query)
            for result in results:
                result["category"] = phase_id
                result["original_query"] = query
            search_results.extend(results)
            await asyncio.sleep(0.5)  # Rate limiting

        # Remove duplicates by URL
        seen_urls = set()
        unique_results = []
        for result in search_results:
            if result["url"] not in seen_urls:
                seen_urls.add(result["url"])
                unique_results.append(result)

        # Fetch content from top results
        urls_to_fetch = [r["url"] for r in unique_results[:results_per_query * 2]]
        fetched_content = await self.fetcher.fetch_multiple(urls_to_fetch)

        # Create research sources
        sources = []
        for content in fetched_content:
            if content.get("type") != "error":
                sources.append(ResearchSource(
                    url=content["url"],
                    title=content.get("title", ""),
                    content=content.get("content", ""),
                    category=phase_id,
                    type=self.fetcher.classify_source_type(
                        content["url"],
                        content.get("content", "")
                    )
                ))

        # Add to project research
        if sources:
            response = await self.research.add_research(project_id, sources)
            return {
                "sources_added": response.added_count,
                "files": response.files_created
            }

        return {"sources_added": 0, "files": []}

    def _extract_brief_variables(self, brief_data: dict[str, Any]) -> dict[str, str]:
        """
        Extract template variables from brief data.

        Args:
            brief_data: Parsed brief information

        Returns:
            Variables dict for query templates
        """
        current_year = datetime.utcnow().year

        return {
            "brand": brief_data.get("brand", brief_data.get("client", "")),
            "industry": brief_data.get("industry", brief_data.get("category", "")),
            "country": brief_data.get("country", "Paraguay"),
            "target_audience": brief_data.get("target_audience", brief_data.get("target", "")),
            "year": str(current_year),
            "season": brief_data.get("season", ""),
            "campaign_type": brief_data.get("campaign_type", ""),
            "objective": brief_data.get("objective", "")
        }

    def _generate_queries(
        self,
        templates: list[str],
        variables: dict[str, str]
    ) -> list[str]:
        """
        Generate search queries from templates and variables.

        Args:
            templates: Query template strings
            variables: Variable values to substitute

        Returns:
            List of generated queries
        """
        queries = []

        for template in templates:
            try:
                query = template.format(**variables)
                # Clean up query
                query = " ".join(query.split())
                if query and len(query) > 5:
                    queries.append(query)
            except KeyError as e:
                logger.debug(f"Missing variable in template: {e}")
                # Try with available variables only
                partial_query = template
                for key, value in variables.items():
                    partial_query = partial_query.replace(f"{{{key}}}", value)
                # Remove unfilled placeholders
                import re
                partial_query = re.sub(r'\{[^}]+\}', '', partial_query)
                partial_query = " ".join(partial_query.split())
                if partial_query and len(partial_query) > 5:
                    queries.append(partial_query)

        return queries

    async def _generate_summary_documents(
        self,
        project_id: str,
        results: dict[str, Any]
    ) -> None:
        """
        Generate summary documents after research completion.

        Args:
            project_id: Project identifier
            results: Research results
        """
        logger.info(f"Generating summary documents for project: {project_id}")

        # Get all research content
        all_research = await self.research.get_all_research(project_id)

        if not all_research:
            logger.warning("No research content to summarize")
            return

        # Generate QUICK-REFERENCE
        await self._generate_quick_reference(project_id, all_research)

        # Generate RESUMEN-EJECUTIVO
        await self._generate_executive_summary(project_id, all_research)

        # Generate INSIGHTS-CREATIVOS
        await self._generate_creative_insights(project_id, all_research)

    async def _generate_quick_reference(self, project_id: str, content: str) -> None:
        """Generate QUICK-REFERENCE.md summary document."""
        # This would use AI to summarize into 1-page format
        logger.info(f"Generating QUICK-REFERENCE for {project_id}")
        # Implementation would call AI service

    async def _generate_executive_summary(self, project_id: str, content: str) -> None:
        """Generate RESUMEN-EJECUTIVO.md summary document."""
        logger.info(f"Generating RESUMEN-EJECUTIVO for {project_id}")
        # Implementation would call AI service

    async def _generate_creative_insights(self, project_id: str, content: str) -> None:
        """Generate INSIGHTS-CREATIVOS.md summary document."""
        logger.info(f"Generating INSIGHTS-CREATIVOS for {project_id}")
        # Implementation would call AI service

    async def run_single_phase(
        self,
        project_id: str,
        phase_id: str,
        brief_data: dict[str, Any],
        results_per_query: int = 5
    ) -> dict[str, Any]:
        """
        Run a single research phase.

        Args:
            project_id: Project identifier
            phase_id: Phase to run
            brief_data: Brief information
            results_per_query: Results per query

        Returns:
            Phase results
        """
        variables = self._extract_brief_variables(brief_data)
        return await self._run_phase(
            project_id,
            phase_id,
            variables,
            results_per_query
        )

    async def expand_research(
        self,
        project_id: str,
        gaps: list[str],
        brief_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Expand research to fill identified gaps.

        Args:
            project_id: Project identifier
            gaps: List of identified research gaps
            brief_data: Brief information

        Returns:
            Expanded research results
        """
        logger.info(f"Expanding research for {len(gaps)} gaps")

        variables = self._extract_brief_variables(brief_data)
        results = {
            "gaps_addressed": [],
            "sources_added": 0,
            "files_created": []
        }

        for gap in gaps:
            # Generate specific queries for each gap
            queries = [
                f"{gap} {variables['country']} {variables['year']}",
                f"{variables['brand']} {gap}",
                f"{variables['industry']} {gap} statistics"
            ]

            search_results = []
            for query in queries:
                search_result = await self.search.search(query, 3)
                search_results.extend(search_result)
                await asyncio.sleep(0.5)

            # Fetch and add to research
            if search_results:
                urls = [r["url"] for r in search_results[:5]]
                fetched = await self.fetcher.fetch_multiple(urls)

                sources = []
                for content in fetched:
                    if content.get("type") != "error":
                        sources.append(ResearchSource(
                            url=content["url"],
                            title=content.get("title", ""),
                            content=content.get("content", ""),
                            category="09-nuevos-hallazgos",
                            type="gap_research"
                        ))

                if sources:
                    response = await self.research.add_research(project_id, sources)
                    results["sources_added"] += response.added_count
                    results["files_created"].extend(response.files_created)
                    results["gaps_addressed"].append(gap)

        return results

    def get_phase_info(self) -> dict[str, Any]:
        """
        Get information about all research phases.

        Returns:
            Phase configuration dictionary
        """
        return RESEARCH_PHASES


# =============================================================================
# Standalone Research Runner (for CLI usage)
# =============================================================================

class StandaloneResearchRunner:
    """
    Standalone research runner that can be used outside the API context.
    Uses WebSearch and WebFetch tools directly through Claude Code.
    """

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_research_plan(
        self,
        brand: str,
        industry: str,
        country: str = "Paraguay",
        target_audience: str = "",
        campaign_type: str = ""
    ) -> dict[str, Any]:
        """
        Generate a research plan with all queries to execute.

        Args:
            brand: Brand name
            industry: Industry/category
            country: Target country
            target_audience: Target audience description
            campaign_type: Type of campaign

        Returns:
            Research plan with queries for each phase
        """
        current_year = datetime.utcnow().year

        variables = {
            "brand": brand,
            "industry": industry,
            "country": country,
            "target_audience": target_audience or f"{industry} consumers",
            "year": str(current_year),
            "season": "",
            "campaign_type": campaign_type
        }

        plan = {
            "brand": brand,
            "industry": industry,
            "country": country,
            "generated_at": datetime.utcnow().isoformat(),
            "phases": {}
        }

        for phase_id, config in RESEARCH_PHASES.items():
            queries = []
            for template in config["query_templates"]:
                try:
                    query = template.format(**variables)
                    query = " ".join(query.split())
                    if query:
                        queries.append(query)
                except KeyError:
                    pass

            plan["phases"][phase_id] = {
                "name": config["name"],
                "description": config["description"],
                "queries": queries,
                "min_sources": config["min_sources"]
            }

        return plan

    def format_research_document(
        self,
        title: str,
        category: str,
        content: str,
        sources: list[dict[str, str]],
        statistics: list[str] | None = None
    ) -> str:
        """
        Format research content into a markdown document.

        Args:
            title: Document title
            category: Research category
            content: Main content
            sources: List of source dicts
            statistics: Key statistics

        Returns:
            Formatted markdown document
        """
        doc = f"# {title}\n\n"
        doc += f"**Categoría:** {category}\n"
        doc += f"**Fecha:** {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
        doc += "---\n\n"

        doc += "## Contenido\n\n"
        doc += content + "\n\n"

        if statistics:
            doc += "## Estadísticas Clave\n\n"
            for stat in statistics:
                doc += f"- {stat}\n"
            doc += "\n"

        if sources:
            doc += "## Fuentes\n\n"
            for source in sources:
                url = source.get("url", "")
                source_title = source.get("title", url)
                accessed = source.get("accessed", datetime.utcnow().strftime('%Y-%m-%d'))
                doc += f"- [{source_title}]({url}) - Accedido: {accessed}\n"

        return doc


# =============================================================================
# Singleton Access
# =============================================================================

_automation_service: ResearchAutomationService | None = None


def get_research_automation_service() -> ResearchAutomationService:
    """Get singleton research automation service."""
    global _automation_service
    if _automation_service is None:
        _automation_service = ResearchAutomationService()
    return _automation_service
