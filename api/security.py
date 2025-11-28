"""
Security module for Campaign Generator API.

Provides API key authentication, rate limiting, and input validation.
"""

import hashlib
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import get_settings
from .logging_config import generate_request_id, get_logger, set_request_id

logger = get_logger("security")

# =============================================================================
# API Key Authentication
# =============================================================================

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """
    Verify API key from request header.

    Args:
        api_key: API key from X-API-Key header

    Returns:
        The verified API key

    Raises:
        HTTPException: If API key is missing or invalid
    """
    settings = get_settings()

    # If no API key is configured, skip authentication (development mode)
    if not settings.api_key:
        logger.warning("No API key configured - authentication disabled")
        return "development"

    if not api_key:
        logger.warning("Missing API key in request")
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # Constant-time comparison to prevent timing attacks
    if not _secure_compare(api_key, settings.api_key):
        logger.warning("Invalid API key attempt")
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    return api_key


def _secure_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a.encode(), b.encode()):
        result |= x ^ y
    return result == 0


# =============================================================================
# Rate Limiting
# =============================================================================

class RateLimiter:
    """
    Simple in-memory rate limiter.

    For production, use Redis-based rate limiting.
    """

    def __init__(self):
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.settings = get_settings()

    def is_allowed(self, key: str, limit: int = None, window: int = None) -> bool:
        """
        Check if request is allowed under rate limit.

        Args:
            key: Identifier for the client (IP or API key)
            limit: Max requests per window (default from settings)
            window: Time window in seconds (default from settings)

        Returns:
            True if allowed, False if rate limited
        """
        if limit is None:
            limit = self.settings.rate_limit_requests
        if window is None:
            window = self.settings.rate_limit_window

        now = time.time()
        window_start = now - window

        # Clean old requests
        self.requests[key] = [
            t for t in self.requests[key]
            if t > window_start
        ]

        # Check limit
        if len(self.requests[key]) >= limit:
            return False

        # Record request
        self.requests[key].append(now)
        return True

    def get_retry_after(self, key: str, window: int = None) -> int:
        """Get seconds until rate limit resets."""
        if window is None:
            window = self.settings.rate_limit_window

        if not self.requests[key]:
            return 0

        oldest = min(self.requests[key])
        retry_after = int(oldest + window - time.time())
        return max(0, retry_after)


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce rate limiting on all requests.
    """

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        # Skip rate limiting if disabled
        if not settings.rate_limit_enabled:
            return await call_next(request)

        # Skip health checks
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Get client identifier (API key or IP)
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            client_id = f"key:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"
        else:
            client_id = f"ip:{request.client.host if request.client else 'unknown'}"

        # Check rate limit
        limiter = get_rate_limiter()
        if not limiter.is_allowed(client_id):
            retry_after = limiter.get_retry_after(client_id)
            logger.warning(f"Rate limit exceeded for {client_id}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please slow down.",
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )

        return await call_next(request)


# =============================================================================
# Input Validation Helpers
# =============================================================================

def validate_filename(filename: str) -> str:
    """
    Validate filename to prevent path traversal attacks.

    Args:
        filename: The filename to validate

    Returns:
        The validated filename

    Raises:
        HTTPException: If filename contains invalid characters
    """
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Check for path traversal attempts
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        logger.warning(f"Path traversal attempt detected: {filename}")
        raise HTTPException(
            status_code=400,
            detail="Invalid filename: path traversal not allowed"
        )

    # Check for invalid characters
    invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
    if any(char in filename for char in invalid_chars):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename: contains forbidden characters"
        )

    return filename


def validate_project_id(project_id: str) -> str:
    """
    Validate project ID format.

    Args:
        project_id: The project ID to validate

    Returns:
        The validated project ID

    Raises:
        HTTPException: If project ID format is invalid
    """
    if not project_id:
        raise HTTPException(status_code=400, detail="Project ID is required")

    # Check length
    if len(project_id) > 100:
        raise HTTPException(
            status_code=400,
            detail="Project ID too long (max 100 characters)"
        )

    # Check for path traversal
    if ".." in project_id or "/" in project_id or "\\" in project_id:
        logger.warning(f"Path traversal attempt in project ID: {project_id}")
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID format"
        )

    return project_id


# =============================================================================
# Security Headers Middleware
# =============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Remove server header
        if "server" in response.headers:
            del response.headers["server"]

        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Add request ID to each request for tracing.

    - Generates unique ID for each request
    - Checks for X-Request-ID header (allows client to provide ID)
    - Adds X-Request-ID to response headers
    - Sets request ID in context for logging
    """

    async def dispatch(self, request: Request, call_next):
        # Get request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = generate_request_id()

        # Set in context for logging
        set_request_id(request_id)

        # Store in request state for route access
        request.state.request_id = request_id

        # Log request start
        logger.info(
            f"{request.method} {request.url.path}",
            extra={"request_id": request_id}
        )

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Log request completion
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code}",
            extra={"request_id": request_id, "status_code": response.status_code}
        )

        return response
