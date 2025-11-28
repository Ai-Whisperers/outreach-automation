"""
Web Search Service

Performs web searches and fetches content from search results.
Uses DuckDuckGo as a free alternative to Google Custom Search.
"""

import asyncio
from urllib.parse import quote_plus

import aiohttp

from ..exceptions import CampaignGeneratorError
from ..logging_config import get_logger

logger = get_logger("web_search")


class WebSearchError(CampaignGeneratorError):
    """Raised when web search fails."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=message,
            error_code="WEB_SEARCH_ERROR",
            details=details or {}
        )


class WebSearchService:
    """
    Service for performing web searches and fetching content.
    Uses DuckDuckGo HTML for free, no-API-key searches.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    async def search(
        self,
        query: str,
        num_results: int = 5,
        region: str = "py-es"  # Paraguay Spanish
    ) -> list[dict]:
        """
        Perform a web search and return results.

        Args:
            query: Search query
            num_results: Number of results to return
            region: Region code for localized results

        Returns:
            List of search results with url, title, snippet
        """
        try:
            # Use DuckDuckGo HTML search
            encoded_query = quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded_query}&kl={region}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=30) as response:
                    if response.status != 200:
                        logger.warning(f"Search returned status {response.status}")
                        return []

                    html = await response.text()
                    results = self._parse_duckduckgo_html(html, num_results)

                    logger.info(f"Search '{query}' returned {len(results)} results")
                    return results

        except TimeoutError:
            logger.error(f"Search timeout for query: {query}")
            return []
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _parse_duckduckgo_html(self, html: str, num_results: int) -> list[dict]:
        """Parse DuckDuckGo HTML results."""
        results = []

        try:
            # Simple parsing without BeautifulSoup
            # Look for result links
            import re

            # Find result blocks
            result_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>([^<]+)</a>'
            snippet_pattern = r'<a class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>)*[^<]*)</a>'

            links = re.findall(result_pattern, html)
            snippets = re.findall(snippet_pattern, html)

            for i, (url, title) in enumerate(links[:num_results]):
                snippet = snippets[i] if i < len(snippets) else ""
                # Clean snippet of HTML tags
                snippet = re.sub(r'<[^>]+>', '', snippet).strip()

                # Skip DuckDuckGo internal links
                if 'duckduckgo.com' in url:
                    continue

                results.append({
                    "url": url,
                    "title": title.strip(),
                    "snippet": snippet
                })

            return results[:num_results]

        except Exception as e:
            logger.error(f"Failed to parse search results: {e}")
            return []

    async def search_multiple(
        self,
        queries: list[dict],
        results_per_query: int = 3
    ) -> list[dict]:
        """
        Perform multiple searches and aggregate results.

        Args:
            queries: List of query dicts with 'query' and 'category' keys
            results_per_query: Results per query

        Returns:
            Aggregated results with category information
        """
        all_results = []

        for query_info in queries:
            query = query_info.get("query", "")
            category = query_info.get("category", "01-mercado-general")

            results = await self.search(query, results_per_query)

            for result in results:
                result["category"] = category
                result["original_query"] = query
                all_results.append(result)

            # Small delay to be polite to the search engine
            await asyncio.sleep(1)

        logger.info(f"Multi-search returned {len(all_results)} total results")
        return all_results


# Singleton
_search_service: WebSearchService | None = None


def get_web_search_service() -> WebSearchService:
    """Get singleton web search service."""
    global _search_service
    if _search_service is None:
        _search_service = WebSearchService()
    return _search_service
