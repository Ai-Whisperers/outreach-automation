"""
Service tests for LinkedInService.

Tests cover:
- Connection request sending
- Message sending
- Status checking
- MockLinkedInService behavior
- Error handling
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestMockLinkedInService:
    """Tests for MockLinkedInService (testing double)."""

    @pytest.fixture
    def mock_service(self):
        """Create MockLinkedInService instance."""
        from api.services.linkedin_service import MockLinkedInService

        return MockLinkedInService()

    @pytest.mark.asyncio
    async def test_send_connection_request_success(self, mock_service):
        """Test mock connection request returns success."""
        result = await mock_service.send_connection_request(
            profile_url="https://linkedin.com/in/johndoe",
            message="Hi John, let's connect!",
        )

        assert result["success"] is True
        assert "request_id" in result

    @pytest.mark.asyncio
    async def test_send_connection_request_tracks_sent(self, mock_service):
        """Test mock service tracks sent requests."""
        await mock_service.send_connection_request(
            profile_url="https://linkedin.com/in/johndoe",
            message="Hi John!",
        )

        assert len(mock_service.sent_requests) == 1
        assert "johndoe" in mock_service.sent_requests[0]["profile_url"]

    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_service):
        """Test mock message sending returns success."""
        result = await mock_service.send_message(
            profile_url="https://linkedin.com/in/johndoe",
            message="Thanks for connecting, John!",
        )

        assert result["success"] is True
        assert "message_id" in result

    @pytest.mark.asyncio
    async def test_send_message_tracks_sent(self, mock_service):
        """Test mock service tracks sent messages."""
        await mock_service.send_message(
            profile_url="https://linkedin.com/in/johndoe",
            message="Hello!",
        )

        assert len(mock_service.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_check_connection_status_pending(self, mock_service):
        """Test checking connection status returns pending."""
        result = await mock_service.check_connection_status(
            profile_url="https://linkedin.com/in/johndoe"
        )

        assert result in ["pending", "connected", "not_connected"]

    @pytest.mark.asyncio
    async def test_clear_history(self, mock_service):
        """Test clearing sent history."""
        await mock_service.send_connection_request(
            profile_url="https://linkedin.com/in/johndoe",
            message="Hi!",
        )
        await mock_service.send_message(
            profile_url="https://linkedin.com/in/johndoe",
            message="Hello!",
        )

        mock_service.clear()

        assert len(mock_service.sent_requests) == 0
        assert len(mock_service.sent_messages) == 0

    @pytest.mark.asyncio
    async def test_simulate_connection_accepted(self, mock_service):
        """Test simulating connection acceptance."""
        mock_service.set_connection_status("https://linkedin.com/in/johndoe", "connected")

        status = await mock_service.check_connection_status(
            profile_url="https://linkedin.com/in/johndoe"
        )

        assert status == "connected"


class TestLinkedInServiceValidation:
    """Tests for LinkedIn message validation."""

    @pytest.fixture
    def service(self):
        """Create LinkedInService."""
        from api.services.linkedin_service import LinkedInService

        return LinkedInService()

    def test_validate_connection_message_length(self, service):
        """Test connection message length validation."""
        # Valid length
        valid_msg = "Hi John, let's connect!" * 3  # Under 200 chars
        assert service.validate_connection_message(valid_msg) is True

        # Too long
        long_msg = "x" * 201
        assert service.validate_connection_message(long_msg) is False

    def test_validate_profile_url(self, service):
        """Test LinkedIn profile URL validation."""
        valid_urls = [
            "https://linkedin.com/in/johndoe",
            "https://www.linkedin.com/in/johndoe",
            "http://linkedin.com/in/johndoe",
        ]

        for url in valid_urls:
            assert service.validate_profile_url(url) is True

    def test_validate_invalid_profile_url(self, service):
        """Test invalid LinkedIn URL validation."""
        invalid_urls = [
            "https://twitter.com/johndoe",
            "not-a-url",
            "",
        ]

        for url in invalid_urls:
            assert service.validate_profile_url(url) is False

    def test_extract_profile_id(self, service):
        """Test extracting profile ID from URL."""
        url = "https://linkedin.com/in/johndoe123"
        profile_id = service.extract_profile_id(url)

        assert profile_id == "johndoe123"

    def test_extract_profile_id_with_params(self, service):
        """Test extracting profile ID from URL with query params."""
        url = "https://linkedin.com/in/johndoe?source=search"
        profile_id = service.extract_profile_id(url)

        assert profile_id == "johndoe"


class TestLinkedInRateLimiting:
    """Tests for LinkedIn rate limiting."""

    @pytest.fixture
    def service_with_limiter(self):
        """Create LinkedInService with mocked rate limiter."""
        from api.services.linkedin_service import LinkedInService

        service = LinkedInService()
        service._rate_limiter = MagicMock()
        service._rate_limiter.check_quota = AsyncMock(return_value=(True, 15))
        service._rate_limiter.increment_usage = AsyncMock(return_value=6)
        return service

    @pytest.mark.asyncio
    async def test_check_quota_before_connection_request(self, service_with_limiter):
        """Test quota is checked before sending connection request."""
        service = service_with_limiter
        service._browser = MagicMock()
        service._send_connection = AsyncMock(return_value={"success": True})

        await service.send_connection_request(
            profile_url="https://linkedin.com/in/johndoe",
            message="Hi!",
            campaign_id=1,
        )

        service._rate_limiter.check_quota.assert_called()

    @pytest.mark.asyncio
    async def test_quota_exceeded_raises_error(self, service_with_limiter):
        """Test quota exceeded raises appropriate error."""
        service = service_with_limiter
        service._rate_limiter.check_quota = AsyncMock(return_value=(False, 0))

        with pytest.raises(Exception) as exc_info:
            await service.send_connection_request(
                profile_url="https://linkedin.com/in/johndoe",
                message="Hi!",
                campaign_id=1,
            )

        assert "quota" in str(exc_info.value).lower()


class TestLinkedInConnectionFlow:
    """Tests for LinkedIn connection workflow."""

    @pytest.fixture
    def mock_service(self):
        """Create MockLinkedInService for flow testing."""
        from api.services.linkedin_service import MockLinkedInService

        return MockLinkedInService()

    @pytest.mark.asyncio
    async def test_connection_workflow(self, mock_service):
        """Test complete connection workflow."""
        profile_url = "https://linkedin.com/in/johndoe"

        # 1. Check initial status
        initial_status = await mock_service.check_connection_status(profile_url)
        assert initial_status == "not_connected"

        # 2. Send connection request
        result = await mock_service.send_connection_request(
            profile_url=profile_url,
            message="Hi John!",
        )
        assert result["success"] is True

        # 3. Simulate acceptance
        mock_service.set_connection_status(profile_url, "connected")

        # 4. Check updated status
        new_status = await mock_service.check_connection_status(profile_url)
        assert new_status == "connected"

        # 5. Send follow-up message
        msg_result = await mock_service.send_message(
            profile_url=profile_url,
            message="Thanks for connecting!",
        )
        assert msg_result["success"] is True

    @pytest.mark.asyncio
    async def test_cannot_message_without_connection(self, mock_service):
        """Test messaging requires connection."""
        profile_url = "https://linkedin.com/in/stranger"

        # Try to send message without connection
        result = await mock_service.send_message(
            profile_url=profile_url,
            message="Hello stranger!",
            require_connection=True,
        )

        assert result.get("success") is False or "not_connected" in str(result)


class TestLinkedInMessagePersonalization:
    """Tests for LinkedIn message personalization."""

    @pytest.fixture
    def service(self):
        """Create LinkedInService."""
        from api.services.linkedin_service import LinkedInService

        return LinkedInService()

    def test_personalize_connection_message(self, service):
        """Test personalizing connection message."""
        template = "Hi {{first_name}}, noticed your work at {{company}}!"
        variables = {
            "first_name": "John",
            "company": "Acme Corp",
        }

        result = service.personalize_message(template, variables)

        assert "John" in result
        assert "Acme Corp" in result

    def test_truncate_long_message(self, service):
        """Test truncating messages that are too long."""
        long_message = "Hi John! " + "x" * 300

        result = service.truncate_for_connection(long_message)

        assert len(result) <= 200

    def test_truncate_preserves_meaning(self, service):
        """Test truncation preserves sentence structure."""
        message = (
            "Hi John, I noticed your excellent work at Acme Corp. "
            "Your team has been doing amazing things with AI. "
            "I'd love to connect and share how we've helped similar companies. "
            "Would you be open to a chat?"
        )

        result = service.truncate_for_connection(message)

        assert len(result) <= 200
        # Should end at sentence boundary or with ellipsis
        assert result.endswith(".") or result.endswith("...")


class TestLinkedInSessionManagement:
    """Tests for LinkedIn session/browser management."""

    @pytest.fixture
    def service(self):
        """Create LinkedInService."""
        from api.services.linkedin_service import LinkedInService

        return LinkedInService()

    @pytest.mark.asyncio
    async def test_initialize_session(self, service):
        """Test session initialization."""
        with patch("playwright.async_api.async_playwright") as mock_pw:
            mock_browser = MagicMock()
            mock_pw.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                chromium=MagicMock(
                    launch=AsyncMock(return_value=mock_browser)
                )
            ))

            await service.initialize_session()

            assert service._browser is not None or mock_pw.called

    @pytest.mark.asyncio
    async def test_close_session(self, service):
        """Test session cleanup."""
        service._browser = MagicMock()
        service._browser.close = AsyncMock()

        await service.close_session()

        service._browser.close.assert_called_once()


class TestLinkedInErrorHandling:
    """Tests for LinkedIn service error handling."""

    @pytest.fixture
    def service(self):
        """Create LinkedInService."""
        from api.services.linkedin_service import LinkedInService

        return LinkedInService()

    @pytest.mark.asyncio
    async def test_handles_network_error(self, service):
        """Test handling network errors gracefully."""
        service._browser = MagicMock()
        service._send_connection = AsyncMock(side_effect=Exception("Network error"))

        result = await service.send_connection_request(
            profile_url="https://linkedin.com/in/johndoe",
            message="Hi!",
        )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_handles_profile_not_found(self, service):
        """Test handling profile not found."""
        service._browser = MagicMock()
        service._send_connection = AsyncMock(return_value={
            "success": False,
            "error": "Profile not found",
        })

        result = await service.send_connection_request(
            profile_url="https://linkedin.com/in/nonexistent",
            message="Hi!",
        )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_handles_already_connected(self, service):
        """Test handling already connected users."""
        service._browser = MagicMock()
        service._check_connection = AsyncMock(return_value="connected")

        result = await service.send_connection_request(
            profile_url="https://linkedin.com/in/johndoe",
            message="Hi!",
        )

        # Should not error, just skip
        assert result.get("skipped") is True or result.get("already_connected") is True


class TestLinkedInEventTracking:
    """Tests for LinkedIn event tracking."""

    @pytest.fixture
    def mock_service(self):
        """Create MockLinkedInService."""
        from api.services.linkedin_service import MockLinkedInService

        return MockLinkedInService()

    @pytest.mark.asyncio
    async def test_track_connection_accepted(self, mock_service):
        """Test tracking connection acceptance event."""
        profile_url = "https://linkedin.com/in/johndoe"

        # Send connection
        await mock_service.send_connection_request(profile_url, "Hi!")

        # Simulate acceptance
        mock_service.set_connection_status(profile_url, "connected")

        event = await mock_service.check_for_acceptance_event(profile_url)

        assert event is not None
        assert event["event_type"] == "connection_accepted"

    @pytest.mark.asyncio
    async def test_track_message_read(self, mock_service):
        """Test tracking message read event."""
        profile_url = "https://linkedin.com/in/johndoe"
        mock_service.set_connection_status(profile_url, "connected")

        # Send message
        await mock_service.send_message(profile_url, "Hello!")

        # Simulate read
        mock_service.set_message_read(profile_url, True)

        event = await mock_service.check_for_read_event(profile_url)

        assert event is not None
        assert event["event_type"] == "message_read"
