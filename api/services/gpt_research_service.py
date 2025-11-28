"""
GPT Researcher Service

Adapter for the gpt-researcher library to conduct deep autonomous research.
"""

import os

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger("gpt_research_service")


class GPTResearchService:
    """
    Service for conducting deep research using Tavily and LLM.
    """

    def __init__(self):
        # Explicitly load environment variables to ensure keys are available
        from dotenv import load_dotenv

        load_dotenv()

        self.settings = get_settings()
        self.ai_manager = None  # Lazy load to avoid circular imports

        # Debug: Check keys and manually inject if missing from settings but present in env
        t_key = self.settings.tavily_api_key or os.getenv("TAVILY_API_KEY")
        if t_key:
            logger.info(f"Tavily Key found: {t_key[:5]}...")
            if not self.settings.tavily_api_key:
                self.settings.tavily_api_key = t_key
        else:
            logger.error("CRITICAL: TAVILY_API_KEY NOT FOUND in Settings or Env!")

        # Ensure API keys are set
        if not self.settings.tavily_api_key:
            logger.warning("TAVILY_API_KEY not set in settings")

        if not self.settings.openai_api_key:
            logger.warning("OPENAI_API_KEY not set in settings")

    async def conduct_research(self, query: str, report_type: str = "research_report") -> str:
        """
        Conduct deep research on a query using Tavily for search and LLM for synthesis.

        Args:
            query: Research query or topic
            report_type: Type of report (ignored in this custom implementation, always returns markdown)

        Returns:
            Research report content
        """
        logger.info(f"Starting Custom Research for query: {query}")

        try:
            # 1. Search using Tavily
            from tavily import TavilyClient

            tavily = TavilyClient(api_key=self.settings.tavily_api_key)
            logger.info("Searching Tavily...")
            search_result = tavily.search(query, search_depth="advanced", max_results=7)

            results = search_result.get("results", [])
            if not results:
                return "No research results found."

            # Format context
            context = "\n\n".join(
                [f"Source: {r['title']}\nURL: {r['url']}\nContent: {r['content']}" for r in results]
            )

            # 2. Synthesize using LLM
            from .ai_client import get_ai_manager

            if not self.ai_manager:
                self.ai_manager = get_ai_manager()

            prompt = f"""
            You are a Senior Market Researcher. Write a comprehensive research report based ONLY on the following search results.
            
            QUERY: {query}
            
            SEARCH RESULTS:
            {context}
            
            INSTRUCTIONS:
            - Structure the report with clear headings (Markdown).
            - Focus on facts, statistics, and concrete details found in the results.
            - Cite sources where possible (e.g., [Source Name]).
            - If the results are insufficient, state what is missing.
            - Write in a professional, analytical tone.
            """

            logger.info("Synthesizing report with LLM...")
            report = await self.ai_manager.generate(prompt, temperature=0.3)

            return report

        except Exception as e:
            logger.error(f"Custom Research failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return f"Research failed: {str(e)}"


# Singleton
_gpt_research_service: GPTResearchService | None = None


def get_gpt_research_service() -> GPTResearchService:
    global _gpt_research_service
    if _gpt_research_service is None:
        _gpt_research_service = GPTResearchService()
    return _gpt_research_service
