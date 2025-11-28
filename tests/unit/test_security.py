"""
Unit tests for security module.

Tests cover:
- API key authentication
- Rate limiting
- Input validation
- Security middlewares
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


class TestSecureCompare:
    """Tests for secure string comparison."""

    def test_secure_compare_equal_strings(self):
        """Test secure compare returns True for equal strings."""
        from api.security import _secure_compare

        assert _secure_compare("test123", "test123") is True

    def test_secure_compare_different_strings(self):
        """Test secure compare returns False for different strings."""
        from api.security import _secure_compare

        assert _secure_compare("test123", "test456") is False

    def test_secure_compare_different_lengths(self):
        """Test secure compare returns False for different length strings."""
        from api.security import _secure_compare

        assert _secure_compare("short", "longer_string") is False

    def test_secure_compare_empty_strings(self):
        """Test secure compare with empty strings."""
        from api.security import _secure_compare

        assert _secure_compare("", "") is True
        assert _secure_compare("test", "") is False


class TestVerifyApiKey:
    """Tests for API key verification."""

    @pytest.mark.asyncio
    async def test_verify_api_key_valid(self):
        """Test verification with valid API key."""
        from api.security import verify_api_key

        with patch("api.security.get_settings") as mock_settings:
            mock_settings.return_value.api_key = "valid-key-123"

            result = await verify_api_key("valid-key-123")
            assert result == "valid-key-123"

    @pytest.mark.asyncio
    async def test_verify_api_key_invalid(self):
        """Test verification with invalid API key."""
        from api.security import verify_api_key

        with patch("api.security.get_settings") as mock_settings:
            mock_settings.return_value.api_key = "valid-key-123"

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key("wrong-key")

            assert exc_info.value.status_code == 403
            assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_missing(self):
        """Test verification with missing API key."""
        from api.security import verify_api_key

        with patch("api.security.get_settings") as mock_settings:
            mock_settings.return_value.api_key = "valid-key-123"

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(None)

            assert exc_info.value.status_code == 401
            assert "Missing API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_dev_mode(self):
        """Test verification when no API key configured (dev mode)."""
        from api.security import verify_api_key

        with patch("api.security.get_settings") as mock_settings:
            mock_settings.return_value.api_key = ""

            result = await verify_api_key(None)
            assert result == "development"


class TestRateLimiter:
    """Tests for rate limiting."""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter instance."""
        from api.security import RateLimiter

        with patch("api.security.get_settings") as mock_settings:
            mock_settings.return_value.rate_limit_requests = 10
            mock_settings.return_value.rate_limit_window = 60
            return RateLimiter()

    def test_is_allowed_under_limit(self, rate_limiter):
        """Test request allowed when under limit."""
        assert rate_limiter.is_allowed("test-client") is True

    def test_is_allowed_at_limit(self, rate_limiter):
        """Test request blocked when at limit."""
        # Make 10 requests
        for _ in range(10):
            rate_limiter.is_allowed("test-client", limit=10, window=60)

        # 11th should be blocked
        assert rate_limiter.is_allowed("test-client", limit=10, window=60) is False

    def test_is_allowed_different_clients(self, rate_limiter):
        """Test rate limits are per-client."""
        # Max out client A
        for _ in range(10):
            rate_limiter.is_allowed("client-a", limit=10, window=60)

        # Client B should still be allowed
        assert rate_limiter.is_allowed("client-b", limit=10, window=60) is True

    def test_is_allowed_window_reset(self, rate_limiter):
        """Test rate limit resets after window."""
        # Make requests
        rate_limiter.requests["test-client"] = [time.time() - 120]  # 2 minutes ago

        # Should be allowed (old requests cleaned)
        assert rate_limiter.is_allowed("test-client", limit=10, window=60) is True

    def test_get_retry_after(self, rate_limiter):
        """Test retry-after calculation."""
        # No requests yet
        assert rate_limiter.get_retry_after("new-client") == 0

        # Make a request
        rate_limiter.requests["test-client"] = [time.time()]

        retry_after = rate_limiter.get_retry_after("test-client", window=60)
        assert 55 <= retry_after <= 60


class TestRateLimiterSingleton:
    """Tests for rate limiter singleton."""

    def test_get_rate_limiter_returns_same_instance(self):
        """Test singleton pattern."""
        from api.security import get_rate_limiter

        with patch("api.security.get_settings") as mock_settings:
            mock_settings.return_value.rate_limit_requests = 100
            mock_settings.return_value.rate_limit_window = 60

            # Reset singleton
            import api.security
            api.security._rate_limiter = None

            limiter1 = get_rate_limiter()
            limiter2 = get_rate_limiter()

            assert limiter1 is limiter2


class TestValidateFilename:
    """Tests for filename validation."""

    def test_validate_valid_filename(self):
        """Test valid filename passes."""
        from api.security import validate_filename

        assert validate_filename("report.pdf") == "report.pdf"
        assert validate_filename("my-file_2024.txt") == "my-file_2024.txt"

    def test_validate_filename_empty(self):
        """Test empty filename raises error."""
        from api.security import validate_filename

        with pytest.raises(HTTPException) as exc_info:
            validate_filename("")

        assert exc_info.value.status_code == 400
        assert "required" in exc_info.value.detail.lower()

    def test_validate_filename_path_traversal(self):
        """Test path traversal attempts are blocked."""
        from api.security import validate_filename

        traversal_attempts = [
            "../etc/passwd",
            "..\\windows\\system32",
            "/etc/passwd",
            "\\windows\\system32",
        ]

        for filename in traversal_attempts:
            with pytest.raises(HTTPException) as exc_info:
                validate_filename(filename)

            assert exc_info.value.status_code == 400
            assert "traversal" in exc_info.value.detail.lower()

    def test_validate_filename_invalid_chars(self):
        """Test invalid characters are blocked."""
        from api.security import validate_filename

        invalid_filenames = [
            "file<script>.txt",
            "file>.txt",
            "file:name.txt",
            'file"name.txt',
            "file|name.txt",
            "file?name.txt",
            "file*name.txt",
        ]

        for filename in invalid_filenames:
            with pytest.raises(HTTPException) as exc_info:
                validate_filename(filename)

            assert exc_info.value.status_code == 400


class TestValidateProjectId:
    """Tests for project ID validation."""

    def test_validate_valid_project_id(self):
        """Test valid project ID passes."""
        from api.security import validate_project_id

        assert validate_project_id("my-project-123") == "my-project-123"
        assert validate_project_id("project_name") == "project_name"

    def test_validate_project_id_empty(self):
        """Test empty project ID raises error."""
        from api.security import validate_project_id

        with pytest.raises(HTTPException) as exc_info:
            validate_project_id("")

        assert exc_info.value.status_code == 400
        assert "required" in exc_info.value.detail.lower()

    def test_validate_project_id_too_long(self):
        """Test project ID length limit."""
        from api.security import validate_project_id

        long_id = "a" * 101

        with pytest.raises(HTTPException) as exc_info:
            validate_project_id(long_id)

        assert exc_info.value.status_code == 400
        assert "too long" in exc_info.value.detail.lower()

    def test_validate_project_id_path_traversal(self):
        """Test path traversal in project ID is blocked."""
        from api.security import validate_project_id

        traversal_ids = [
            "../other-project",
            "project/subdir",
            "project\\subdir",
        ]

        for project_id in traversal_ids:
            with pytest.raises(HTTPException) as exc_info:
                validate_project_id(project_id)

            assert exc_info.value.status_code == 400


class TestRateLimitMiddleware:
    """Tests for rate limit middleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        from api.security import RateLimitMiddleware

        app = MagicMock()
        return RateLimitMiddleware(app)

    @pytest.mark.asyncio
    async def test_middleware_allows_health_check(self, middleware):
        """Test health check bypasses rate limiting."""
        from api.security import RateLimitMiddleware

        request = MagicMock()
        request.url.path = "/health"
        call_next = AsyncMock(return_value=MagicMock())

        with patch("api.security.get_settings") as mock_settings:
            mock_settings.return_value.rate_limit_enabled = True

            response = await middleware.dispatch(request, call_next)
            call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_middleware_allows_docs(self, middleware):
        """Test docs bypass rate limiting."""
        request = MagicMock()
        request.url.path = "/docs"
        call_next = AsyncMock(return_value=MagicMock())

        with patch("api.security.get_settings") as mock_settings:
            mock_settings.return_value.rate_limit_enabled = True

            response = await middleware.dispatch(request, call_next)
            call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_middleware_disabled(self, middleware):
        """Test middleware bypassed when disabled."""
        request = MagicMock()
        request.url.path = "/api/projects"
        call_next = AsyncMock(return_value=MagicMock())

        with patch("api.security.get_settings") as mock_settings:
            mock_settings.return_value.rate_limit_enabled = False

            response = await middleware.dispatch(request, call_next)
            call_next.assert_called_once()


class TestSecurityHeadersMiddleware:
    """Tests for security headers middleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        from api.security import SecurityHeadersMiddleware

        app = MagicMock()
        return SecurityHeadersMiddleware(app)

    @pytest.mark.asyncio
    async def test_adds_security_headers(self, middleware):
        """Test middleware adds security headers."""
        request = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {}
        call_next = AsyncMock(return_value=mock_response)

        response = await middleware.dispatch(request, call_next)

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "Referrer-Policy" in response.headers


class TestRequestIDMiddleware:
    """Tests for request ID middleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        from api.security import RequestIDMiddleware

        app = MagicMock()
        return RequestIDMiddleware(app)

    @pytest.mark.asyncio
    async def test_generates_request_id(self, middleware):
        """Test middleware generates request ID."""
        request = MagicMock()
        request.headers = {}
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/api/test"

        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        with patch("api.security.generate_request_id", return_value="req-123"):
            with patch("api.security.set_request_id"):
                response = await middleware.dispatch(request, call_next)

        assert response.headers["X-Request-ID"] == "req-123"

    @pytest.mark.asyncio
    async def test_uses_provided_request_id(self, middleware):
        """Test middleware uses client-provided request ID."""
        request = MagicMock()
        request.headers = {"X-Request-ID": "client-provided-id"}
        request.state = MagicMock()
        request.method = "GET"
        request.url.path = "/api/test"

        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.status_code = 200
        call_next = AsyncMock(return_value=mock_response)

        with patch("api.security.set_request_id"):
            response = await middleware.dispatch(request, call_next)

        assert response.headers["X-Request-ID"] == "client-provided-id"
