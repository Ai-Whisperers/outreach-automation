"""
Web Content Fetcher Service

Fetches and extracts content from web URLs for research.
"""

import asyncio
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..exceptions import ContentExtractionError, SourceFetchError
from ..logging_config import get_logger

logger = get_logger("web_fetcher")


# =============================================================================
# Web Fetcher Service
# =============================================================================

class WebFetcherService:
    """
    Service for fetching and extracting content from web pages.
    """

    def __init__(self):
        self.timeout = 30.0
        self.max_content_length = 50000  # characters
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
        }

    async def fetch_url(self, url: str) -> dict[str, Any]:
        """
        Fetch content from a URL.

        Args:
            url: URL to fetch

        Returns:
            Dict with title, content, metadata
        """
        logger.info(f"Fetching URL: {url}")

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True
            ) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")

                if "text/html" in content_type:
                    return await self._extract_html_content(url, response.text)
                elif "application/pdf" in content_type:
                    return self._handle_pdf(url)
                else:
                    return {
                        "url": url,
                        "title": self._extract_domain(url),
                        "content": response.text[:self.max_content_length],
                        "type": "text"
                    }

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching URL: {url}")
            raise SourceFetchError(url, "Request timed out")

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching URL: {url} - {e.response.status_code}")
            raise SourceFetchError(url, f"HTTP {e.response.status_code}")

        except Exception as e:
            logger.error(f"Error fetching URL: {url} - {e}")
            raise SourceFetchError(url, str(e))

    async def _extract_html_content(self, url: str, html: str) -> dict[str, Any]:
        """
        Extract content from HTML page.

        Args:
            url: Source URL
            html: Raw HTML content

        Returns:
            Extracted content dict
        """
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Extract title
            title = ""
            if soup.title:
                title = soup.title.string or ""
            elif soup.find("h1"):
                title = soup.find("h1").get_text()

            # Remove unwanted elements
            for element in soup.find_all([
                "script", "style", "nav", "footer", "header",
                "aside", "form", "iframe", "noscript"
            ]):
                element.decompose()

            # Try to find main content
            main_content = None
            for selector in ["article", "main", "[role='main']", ".content", "#content"]:
                main_content = soup.select_one(selector)
                if main_content:
                    break

            if not main_content:
                main_content = soup.body or soup

            # Extract text
            text = main_content.get_text(separator="\n", strip=True)

            # Clean up text
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            content = "\n".join(lines)

            # Truncate if too long
            if len(content) > self.max_content_length:
                content = content[:self.max_content_length] + "\n\n[Content truncated...]"

            # Extract metadata
            metadata = self._extract_metadata(soup)

            return {
                "url": url,
                "title": title.strip(),
                "content": content,
                "type": "html",
                "metadata": metadata
            }

        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            raise ContentExtractionError(url, str(e))

    def _extract_metadata(self, soup: BeautifulSoup) -> dict[str, str]:
        """Extract metadata from HTML."""
        metadata = {}

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            metadata["description"] = meta_desc.get("content", "")

        # Meta keywords
        meta_keywords = soup.find("meta", attrs={"name": "keywords"})
        if meta_keywords:
            metadata["keywords"] = meta_keywords.get("content", "")

        # Author
        meta_author = soup.find("meta", attrs={"name": "author"})
        if meta_author:
            metadata["author"] = meta_author.get("content", "")

        # Published date
        for attr in ["article:published_time", "datePublished", "pubdate"]:
            date_meta = soup.find("meta", attrs={"property": attr}) or \
                        soup.find("meta", attrs={"name": attr})
            if date_meta:
                metadata["published"] = date_meta.get("content", "")
                break

        return metadata

    def _handle_pdf(self, url: str) -> dict[str, Any]:
        """Handle PDF URLs (placeholder - would need PDF extraction)."""
        return {
            "url": url,
            "title": self._extract_domain(url),
            "content": "[PDF content - extraction not implemented]",
            "type": "pdf"
        }

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc

    async def fetch_multiple(self, urls: list[str]) -> list[dict[str, Any]]:
        """
        Fetch multiple URLs concurrently.

        Args:
            urls: List of URLs to fetch

        Returns:
            List of content dicts
        """
        tasks = [self.fetch_url(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        fetched = []
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch {url}: {result}")
                fetched.append({
                    "url": url,
                    "title": self._extract_domain(url),
                    "content": f"[Error: {result}]",
                    "type": "error",
                    "error": str(result)
                })
            else:
                fetched.append(result)

        return fetched

    def classify_source_type(self, url: str, content: str) -> str:
        """
        Classify the type of source based on URL and content.

        Args:
            url: Source URL
            content: Page content

        Returns:
            Source type string
        """
        url_lower = url.lower()
        content_lower = content.lower()

        # Check for specific source types
        if any(x in url_lower for x in ["statista", "euromonitor", "nielsen", "ibisworld"]):
            return "industry_report"

        if any(x in url_lower for x in ["news", "press", "article", "blog"]):
            return "news_article"

        if any(x in url_lower for x in ["study", "research", "journal", "academic"]):
            return "academic"

        if any(x in url_lower for x in ["facebook", "twitter", "instagram", "linkedin", "tiktok"]):
            return "social_media"

        if any(x in url_lower for x in ["gov", "gob", "gobierno"]):
            return "government"

        if "%" in content_lower or any(x in content_lower for x in ["growth", "market size", "revenue"]):
            return "market_data"

        return "web"


# =============================================================================
# Singleton Access
# =============================================================================

_web_fetcher: WebFetcherService | None = None


def get_web_fetcher() -> WebFetcherService:
    """Get singleton web fetcher service."""
    global _web_fetcher
    if _web_fetcher is None:
        _web_fetcher = WebFetcherService()
    return _web_fetcher
