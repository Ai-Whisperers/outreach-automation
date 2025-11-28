"""
Service tests for web search module.

Tests cover:
- DuckDuckGo HTML search
- Search result parsing
- Multiple query searches
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWebSearchService:
    """Tests for WebSearchService."""

    @pytest.fixture
    def service(self):
        """Create web search service."""
        from api.services.web_search import WebSearchService

        return WebSearchService()

    def test_service_initialization(self, service):
        """Test service initializes with headers."""
        assert "User-Agent" in service.headers
        assert "Mozilla" in service.headers["User-Agent"]

    @pytest.mark.asyncio
    async def test_search_success(self, service):
        """Test successful search."""
        mock_html = """
        <html>
        <a rel="nofollow" class="result__a" href="https://example.com/article1">Article Title 1</a>
        <a class="result__snippet">This is a snippet for article 1</a>
        <a rel="nofollow" class="result__a" href="https://example.com/article2">Article Title 2</a>
        <a class="result__snippet">This is a snippet for article 2</a>
        </html>
        """

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=mock_html)

            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_response

            mock_session_instance = MagicMock()
            mock_session_instance.get.return_value = mock_context
            mock_session_instance.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session_instance.__aexit__ = AsyncMock()

            mock_session.return_value = mock_session_instance

            results = await service.search("test query", num_results=5)

        assert len(results) == 2
        assert results[0]["url"] == "https://example.com/article1"
        assert results[0]["title"] == "Article Title 1"

    @pytest.mark.asyncio
    async def test_search_non_200_status(self, service):
        """Test search with non-200 response."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 404

            mock_context = AsyncMock()
            mock_context.__aenter__.return_value = mock_response

            mock_session_instance = MagicMock()
            mock_session_instance.get.return_value = mock_context
            mock_session_instance.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session_instance.__aexit__ = AsyncMock()

            mock_session.return_value = mock_session_instance

            results = await service.search("test query")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_timeout(self, service):
        """Test search timeout handling."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.get.side_effect = TimeoutError("Request timed out")
            mock_session_instance.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session_instance.__aexit__ = AsyncMock()

            mock_session.return_value = mock_session_instance

            results = await service.search("test query")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_generic_error(self, service):
        """Test search generic error handling."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_session_instance = MagicMock()
            mock_session_instance.get.side_effect = Exception("Network error")
            mock_session_instance.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session_instance.__aexit__ = AsyncMock()

            mock_session.return_value = mock_session_instance

            results = await service.search("test query")

        assert results == []


class TestParseDuckDuckGoHTML:
    """Tests for DuckDuckGo HTML parsing."""

    @pytest.fixture
    def service(self):
        """Create web search service."""
        from api.services.web_search import WebSearchService

        return WebSearchService()

    def test_parse_valid_html(self, service):
        """Test parsing valid HTML."""
        html = """
        <a rel="nofollow" class="result__a" href="https://example.com">Title</a>
        <a class="result__snippet">Snippet text</a>
        """

        results = service._parse_duckduckgo_html(html, num_results=5)

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com"
        assert results[0]["title"] == "Title"
        assert "Snippet" in results[0]["snippet"]

    def test_parse_filters_duckduckgo_links(self, service):
        """Test parsing filters DuckDuckGo internal links."""
        html = """
        <a rel="nofollow" class="result__a" href="https://duckduckgo.com/internal">DDG Link</a>
        <a rel="nofollow" class="result__a" href="https://example.com">Real Link</a>
        """

        results = service._parse_duckduckgo_html(html, num_results=5)

        # Should filter out duckduckgo.com links
        assert len(results) == 1
        assert results[0]["url"] == "https://example.com"

    def test_parse_limits_results(self, service):
        """Test parsing respects num_results limit."""
        html = """
        <a rel="nofollow" class="result__a" href="https://1.com">One</a>
        <a rel="nofollow" class="result__a" href="https://2.com">Two</a>
        <a rel="nofollow" class="result__a" href="https://3.com">Three</a>
        <a rel="nofollow" class="result__a" href="https://4.com">Four</a>
        """

        results = service._parse_duckduckgo_html(html, num_results=2)

        assert len(results) == 2

    def test_parse_empty_html(self, service):
        """Test parsing empty HTML."""
        results = service._parse_duckduckgo_html("", num_results=5)

        assert results == []

    def test_parse_no_results_html(self, service):
        """Test parsing HTML with no results."""
        html = """
        <html>
        <div>No results found</div>
        </html>
        """

        results = service._parse_duckduckgo_html(html, num_results=5)

        assert results == []

    def test_parse_strips_html_from_snippet(self, service):
        """Test parsing strips HTML tags from snippets."""
        html = """
        <a rel="nofollow" class="result__a" href="https://example.com">Title</a>
        <a class="result__snippet">Text with <b>bold</b> and <i>italic</i></a>
        """

        results = service._parse_duckduckgo_html(html, num_results=5)

        # HTML tags should be stripped
        assert "<b>" not in results[0]["snippet"]
        assert "<i>" not in results[0]["snippet"]


class TestSearchMultiple:
    """Tests for multiple query searches."""

    @pytest.fixture
    def service(self):
        """Create web search service."""
        from api.services.web_search import WebSearchService

        return WebSearchService()

    @pytest.mark.asyncio
    async def test_search_multiple_queries(self, service):
        """Test searching multiple queries."""
        queries = [
            {"query": "query one", "category": "category-a"},
            {"query": "query two", "category": "category-b"},
        ]

        with patch.object(service, "search") as mock_search:
            mock_search.return_value = [
                {"url": "https://example.com", "title": "Result", "snippet": "Text"}
            ]

            results = await service.search_multiple(queries, results_per_query=3)

        assert len(results) == 2  # One result per query
        assert results[0]["category"] == "category-a"
        assert results[0]["original_query"] == "query one"
        assert results[1]["category"] == "category-b"

    @pytest.mark.asyncio
    async def test_search_multiple_default_category(self, service):
        """Test default category assignment."""
        queries = [{"query": "test query"}]  # No category specified

        with patch.object(service, "search") as mock_search:
            mock_search.return_value = [
                {"url": "https://example.com", "title": "Result", "snippet": "Text"}
            ]

            results = await service.search_multiple(queries)

        assert results[0]["category"] == "01-mercado-general"

    @pytest.mark.asyncio
    async def test_search_multiple_aggregates_results(self, service):
        """Test multiple queries aggregate results."""
        queries = [
            {"query": "query one", "category": "cat-a"},
            {"query": "query two", "category": "cat-b"},
        ]

        with patch.object(service, "search") as mock_search:
            # Return multiple results per query
            mock_search.return_value = [
                {"url": "https://1.com", "title": "One", "snippet": "1"},
                {"url": "https://2.com", "title": "Two", "snippet": "2"},
            ]

            results = await service.search_multiple(queries, results_per_query=2)

        # 2 queries * 2 results = 4 total
        assert len(results) == 4


class TestWebSearchError:
    """Tests for WebSearchError exception."""

    def test_web_search_error_creation(self):
        """Test WebSearchError creation."""
        from api.services.web_search import WebSearchError

        error = WebSearchError("Search failed", details={"query": "test"})

        assert error.error_code == "WEB_SEARCH_ERROR"
        assert "Search failed" in str(error)
        assert error.details["query"] == "test"

    def test_web_search_error_inheritance(self):
        """Test WebSearchError inherits from CampaignGeneratorError."""
        from api.exceptions import CampaignGeneratorError
        from api.services.web_search import WebSearchError

        error = WebSearchError("Error")

        assert isinstance(error, CampaignGeneratorError)


class TestWebSearchSingleton:
    """Tests for singleton access."""

    def test_get_web_search_service_returns_same_instance(self):
        """Test singleton pattern."""
        # Reset singleton
        import api.services.web_search
        api.services.web_search._search_service = None

        from api.services.web_search import get_web_search_service

        service1 = get_web_search_service()
        service2 = get_web_search_service()

        assert service1 is service2
