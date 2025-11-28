"""
Tests for WebFetcherService.

Tests cover:
- URL fetching
- HTML content extraction
- Metadata extraction
- PDF handling
- Multiple URL fetching
- Source type classification
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import httpx


class TestWebFetcherServiceInit:
    """Tests for WebFetcherService initialization."""

    def test_web_fetcher_initialization(self):
        """Test WebFetcherService initializes correctly."""
        from api.services.web_fetcher import WebFetcherService

        service = WebFetcherService()

        assert service.timeout == 30.0
        assert service.max_content_length == 50000
        assert "User-Agent" in service.headers

    def test_web_fetcher_headers(self):
        """Test WebFetcherService has appropriate headers."""
        from api.services.web_fetcher import WebFetcherService

        service = WebFetcherService()

        assert "Mozilla" in service.headers["User-Agent"]
        assert "Accept" in service.headers
        assert "Accept-Language" in service.headers


class TestFetchURL:
    """Tests for fetch_url method."""

    @pytest.fixture
    def web_fetcher(self):
        """Create WebFetcherService."""
        from api.services.web_fetcher import WebFetcherService

        return WebFetcherService()

    @pytest.mark.asyncio
    async def test_fetch_url_html_success(self, web_fetcher):
        """Test successful HTML fetch."""
        html_content = """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <main>
                <h1>Main Content</h1>
                <p>Some paragraph text.</p>
            </main>
        </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.text = html_content
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            MockClient.return_value = mock_client

            result = await web_fetcher.fetch_url("https://example.com")

            assert result["url"] == "https://example.com"
            assert result["type"] == "html"
            assert "Main Content" in result["content"]

    @pytest.mark.asyncio
    async def test_fetch_url_pdf_handling(self, web_fetcher):
        """Test PDF URL handling."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            MockClient.return_value = mock_client

            result = await web_fetcher.fetch_url("https://example.com/document.pdf")

            assert result["type"] == "pdf"
            assert "PDF" in result["content"]

    @pytest.mark.asyncio
    async def test_fetch_url_plain_text(self, web_fetcher):
        """Test plain text response."""
        mock_response = MagicMock()
        mock_response.text = "Plain text content here"
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            MockClient.return_value = mock_client

            result = await web_fetcher.fetch_url("https://example.com/data.txt")

            assert result["type"] == "text"
            assert "Plain text content" in result["content"]

    @pytest.mark.asyncio
    async def test_fetch_url_timeout_error(self, web_fetcher):
        """Test timeout error handling."""
        from api.exceptions import SourceFetchError

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            MockClient.return_value = mock_client

            with pytest.raises(SourceFetchError) as exc_info:
                await web_fetcher.fetch_url("https://slow-site.com")

            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_fetch_url_http_error(self, web_fetcher):
        """Test HTTP error handling."""
        from api.exceptions import SourceFetchError

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_response
            ))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            MockClient.return_value = mock_client

            with pytest.raises(SourceFetchError) as exc_info:
                await web_fetcher.fetch_url("https://example.com/missing")

            assert "404" in str(exc_info.value)


class TestExtractHTMLContent:
    """Tests for HTML content extraction."""

    @pytest.fixture
    def web_fetcher(self):
        """Create WebFetcherService."""
        from api.services.web_fetcher import WebFetcherService

        return WebFetcherService()

    @pytest.mark.asyncio
    async def test_extract_html_with_title(self, web_fetcher):
        """Test extracting title from HTML."""
        html = """
        <html>
        <head><title>Page Title</title></head>
        <body><p>Content</p></body>
        </html>
        """

        result = await web_fetcher._extract_html_content("https://example.com", html)

        assert result["title"] == "Page Title"

    @pytest.mark.asyncio
    async def test_extract_html_with_h1_fallback(self, web_fetcher):
        """Test title extraction falls back to h1."""
        html = """
        <html>
        <body>
            <h1>Heading Title</h1>
            <p>Content</p>
        </body>
        </html>
        """

        result = await web_fetcher._extract_html_content("https://example.com", html)

        assert result["title"] == "Heading Title"

    @pytest.mark.asyncio
    async def test_extract_html_removes_scripts(self, web_fetcher):
        """Test scripts are removed from content."""
        html = """
        <html>
        <head><title>Test</title></head>
        <body>
            <p>Good content</p>
            <script>alert('bad')</script>
        </body>
        </html>
        """

        result = await web_fetcher._extract_html_content("https://example.com", html)

        assert "alert" not in result["content"]
        assert "Good content" in result["content"]

    @pytest.mark.asyncio
    async def test_extract_html_removes_navigation(self, web_fetcher):
        """Test navigation elements are removed."""
        html = """
        <html>
        <body>
            <nav>Navigation menu</nav>
            <main>Main content here</main>
            <footer>Footer content</footer>
        </body>
        </html>
        """

        result = await web_fetcher._extract_html_content("https://example.com", html)

        assert "Navigation menu" not in result["content"]
        assert "Footer content" not in result["content"]
        assert "Main content" in result["content"]

    @pytest.mark.asyncio
    async def test_extract_html_finds_main_content(self, web_fetcher):
        """Test main content extraction from article tag."""
        html = """
        <html>
        <body>
            <div>Sidebar stuff</div>
            <article>
                <h1>Article Title</h1>
                <p>Article content paragraph.</p>
            </article>
        </body>
        </html>
        """

        result = await web_fetcher._extract_html_content("https://example.com", html)

        assert "Article content" in result["content"]

    @pytest.mark.asyncio
    async def test_extract_html_truncates_long_content(self, web_fetcher):
        """Test long content is truncated."""
        # Create content longer than max_content_length
        long_content = "x" * 60000
        html = f"""
        <html>
        <body>
            <main>{long_content}</main>
        </body>
        </html>
        """

        result = await web_fetcher._extract_html_content("https://example.com", html)

        assert len(result["content"]) <= web_fetcher.max_content_length + 50  # Allow for truncation message
        assert "[Content truncated...]" in result["content"]


class TestExtractMetadata:
    """Tests for metadata extraction."""

    @pytest.fixture
    def web_fetcher(self):
        """Create WebFetcherService."""
        from api.services.web_fetcher import WebFetcherService

        return WebFetcherService()

    def test_extract_metadata_description(self, web_fetcher):
        """Test extracting meta description."""
        from bs4 import BeautifulSoup

        html = """
        <html>
        <head>
            <meta name="description" content="Page description here">
        </head>
        <body></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        metadata = web_fetcher._extract_metadata(soup)

        assert metadata["description"] == "Page description here"

    def test_extract_metadata_keywords(self, web_fetcher):
        """Test extracting meta keywords."""
        from bs4 import BeautifulSoup

        html = """
        <html>
        <head>
            <meta name="keywords" content="keyword1, keyword2, keyword3">
        </head>
        <body></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        metadata = web_fetcher._extract_metadata(soup)

        assert "keyword1" in metadata["keywords"]

    def test_extract_metadata_author(self, web_fetcher):
        """Test extracting meta author."""
        from bs4 import BeautifulSoup

        html = """
        <html>
        <head>
            <meta name="author" content="John Doe">
        </head>
        <body></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        metadata = web_fetcher._extract_metadata(soup)

        assert metadata["author"] == "John Doe"

    def test_extract_metadata_published_date(self, web_fetcher):
        """Test extracting published date."""
        from bs4 import BeautifulSoup

        html = """
        <html>
        <head>
            <meta property="article:published_time" content="2024-01-15T10:00:00Z">
        </head>
        <body></body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        metadata = web_fetcher._extract_metadata(soup)

        assert "2024-01-15" in metadata["published"]


class TestFetchMultiple:
    """Tests for fetch_multiple method."""

    @pytest.fixture
    def web_fetcher(self):
        """Create WebFetcherService."""
        from api.services.web_fetcher import WebFetcherService

        return WebFetcherService()

    @pytest.mark.asyncio
    async def test_fetch_multiple_success(self, web_fetcher):
        """Test fetching multiple URLs."""
        web_fetcher.fetch_url = AsyncMock(side_effect=[
            {"url": "https://example1.com", "content": "Content 1", "type": "html"},
            {"url": "https://example2.com", "content": "Content 2", "type": "html"},
        ])

        urls = ["https://example1.com", "https://example2.com"]
        results = await web_fetcher.fetch_multiple(urls)

        assert len(results) == 2
        assert results[0]["content"] == "Content 1"
        assert results[1]["content"] == "Content 2"

    @pytest.mark.asyncio
    async def test_fetch_multiple_handles_errors(self, web_fetcher):
        """Test fetch_multiple handles individual failures."""
        from api.exceptions import SourceFetchError

        web_fetcher.fetch_url = AsyncMock(side_effect=[
            {"url": "https://example1.com", "content": "Content 1", "type": "html"},
            SourceFetchError("https://example2.com", "Failed"),
        ])

        urls = ["https://example1.com", "https://example2.com"]
        results = await web_fetcher.fetch_multiple(urls)

        assert len(results) == 2
        assert results[0]["content"] == "Content 1"
        assert results[1]["type"] == "error"
        assert "error" in results[1]


class TestClassifySourceType:
    """Tests for source type classification."""

    @pytest.fixture
    def web_fetcher(self):
        """Create WebFetcherService."""
        from api.services.web_fetcher import WebFetcherService

        return WebFetcherService()

    def test_classify_industry_report(self, web_fetcher):
        """Test classifying industry report sources."""
        assert web_fetcher.classify_source_type("https://www.statista.com/report", "") == "industry_report"
        assert web_fetcher.classify_source_type("https://euromonitor.com/study", "") == "industry_report"
        assert web_fetcher.classify_source_type("https://nielsen.com/data", "") == "industry_report"

    def test_classify_news_article(self, web_fetcher):
        """Test classifying news sources."""
        assert web_fetcher.classify_source_type("https://news.example.com/article", "") == "news_article"
        assert web_fetcher.classify_source_type("https://example.com/press-release", "") == "news_article"
        assert web_fetcher.classify_source_type("https://example.com/blog/post", "") == "news_article"

    def test_classify_academic(self, web_fetcher):
        """Test classifying academic sources."""
        assert web_fetcher.classify_source_type("https://journal.org/study/123", "") == "academic"
        assert web_fetcher.classify_source_type("https://academic.edu/research", "") == "academic"

    def test_classify_social_media(self, web_fetcher):
        """Test classifying social media sources."""
        assert web_fetcher.classify_source_type("https://facebook.com/page", "") == "social_media"
        assert web_fetcher.classify_source_type("https://twitter.com/user", "") == "social_media"
        assert web_fetcher.classify_source_type("https://linkedin.com/company", "") == "social_media"

    def test_classify_government(self, web_fetcher):
        """Test classifying government sources."""
        assert web_fetcher.classify_source_type("https://data.gov/stats", "") == "government"
        assert web_fetcher.classify_source_type("https://gob.py/info", "") == "government"

    def test_classify_market_data_from_content(self, web_fetcher):
        """Test classifying market data from content."""
        content = "Market size reached 15% growth rate with revenue of $1B"
        assert web_fetcher.classify_source_type("https://example.com", content) == "market_data"

    def test_classify_generic_web(self, web_fetcher):
        """Test default classification."""
        assert web_fetcher.classify_source_type("https://random-site.com", "No specific indicators") == "web"


class TestExtractDomain:
    """Tests for domain extraction."""

    @pytest.fixture
    def web_fetcher(self):
        """Create WebFetcherService."""
        from api.services.web_fetcher import WebFetcherService

        return WebFetcherService()

    def test_extract_domain_simple(self, web_fetcher):
        """Test extracting domain from URL."""
        assert web_fetcher._extract_domain("https://example.com/page") == "example.com"

    def test_extract_domain_with_subdomain(self, web_fetcher):
        """Test extracting domain with subdomain."""
        assert web_fetcher._extract_domain("https://www.example.com/page") == "www.example.com"

    def test_extract_domain_with_port(self, web_fetcher):
        """Test extracting domain with port."""
        assert web_fetcher._extract_domain("https://example.com:8080/page") == "example.com:8080"


class TestSingleton:
    """Tests for singleton access."""

    def test_get_web_fetcher_singleton(self):
        """Test get_web_fetcher returns singleton."""
        import api.services.web_fetcher as module
        module._web_fetcher = None

        from api.services.web_fetcher import get_web_fetcher

        service1 = get_web_fetcher()
        service2 = get_web_fetcher()

        assert service1 is service2
