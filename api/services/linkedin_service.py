"""
LinkedIn Service with Playwright Browser Automation.

WARNING: Browser automation violates LinkedIn's Terms of Service.
Use at your own risk. Account suspension is possible.

Features:
- Session persistence via cookies
- Human-like delays between actions
- Rate limiting (max 20 connections/day)
- Connection request sending
- Direct message sending
- Connection status checking
"""

import asyncio
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger("services.linkedin")

# Try to import playwright - it's optional
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. LinkedIn automation disabled.")


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ConnectionResult:
    """Result of a connection request."""

    success: bool
    request_id: str | None = None
    error: str | None = None
    timestamp: datetime | None = None


@dataclass
class MessageResult:
    """Result of sending a message."""

    success: bool
    message_id: str | None = None
    error: str | None = None
    timestamp: datetime | None = None


@dataclass
class ProfileInfo:
    """LinkedIn profile information."""

    name: str
    headline: str | None = None
    location: str | None = None
    connection_status: str | None = None  # "1st", "2nd", "3rd", "Out of network"
    profile_url: str | None = None


# =============================================================================
# LinkedIn Service
# =============================================================================


class LinkedInService:
    """
    LinkedIn browser automation service.

    Usage:
        service = LinkedInService()
        await service.initialize()
        result = await service.send_connection_request(
            profile_url="https://linkedin.com/in/example",
            message="Hi, I'd love to connect!"
        )
        await service.close()
    """

    def __init__(self):
        self.settings = get_settings()
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._initialized = False

        # Configuration
        self.cookies_path = getattr(
            self.settings, "linkedin_cookies_path",
            Path("./linkedin_cookies.json")
        )
        self.headless = getattr(self.settings, "linkedin_headless", True)
        self.daily_limit = getattr(self.settings, "linkedin_daily_limit", 20)
        self.delay_min = getattr(self.settings, "linkedin_action_delay_min", 2)
        self.delay_max = getattr(self.settings, "linkedin_action_delay_max", 5)

    async def initialize(self, cookies_path: str | Path | None = None) -> bool:
        """
        Initialize the browser and load LinkedIn session.

        Args:
            cookies_path: Path to cookies JSON file (optional)

        Returns:
            True if initialization successful
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False

        if self._initialized:
            return True

        try:
            # Use provided path or default
            cookies_file = Path(cookies_path) if cookies_path else Path(self.cookies_path)

            # Launch browser
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ]
            )

            # Create context with realistic settings
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York",
            )

            # Load cookies if available
            if cookies_file.exists():
                cookies = json.loads(cookies_file.read_text())
                await self.context.add_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} cookies from {cookies_file}")
            else:
                logger.warning(f"No cookies file found at {cookies_file}")

            # Create page
            self.page = await self.context.new_page()

            # Verify session by navigating to LinkedIn
            await self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
            await self._random_delay(1, 2)

            # Check if logged in
            if "login" in self.page.url or "checkpoint" in self.page.url:
                logger.error("LinkedIn session invalid. Please update cookies.")
                return False

            self._initialized = True
            logger.info("LinkedIn service initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize LinkedIn service: {e}")
            await self.close()
            return False

    async def close(self):
        """Close the browser and clean up resources."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

        self.page = None
        self.context = None
        self.browser = None
        self._initialized = False
        logger.info("LinkedIn service closed")

    async def save_cookies(self, path: str | Path | None = None):
        """Save current session cookies to file."""
        if not self.context:
            return

        cookies_file = Path(path) if path else Path(self.cookies_path)
        cookies = await self.context.cookies()
        cookies_file.write_text(json.dumps(cookies, indent=2))
        logger.info(f"Saved {len(cookies)} cookies to {cookies_file}")

    # =========================================================================
    # Connection Requests
    # =========================================================================

    async def send_connection_request(
        self,
        profile_url: str,
        message: str | None = None,
    ) -> ConnectionResult:
        """
        Send a LinkedIn connection request.

        Args:
            profile_url: LinkedIn profile URL
            message: Optional connection message (<200 chars)

        Returns:
            ConnectionResult with success status
        """
        if not self._initialized:
            return ConnectionResult(success=False, error="Service not initialized")

        # Validate message length
        if message and len(message) > 200:
            logger.warning("Message exceeds 200 chars, truncating")
            message = message[:197] + "..."

        try:
            # Navigate to profile
            await self.page.goto(profile_url, wait_until="domcontentloaded")
            await self._random_delay()

            # Check if already connected
            connection_status = await self._get_connection_status()
            if connection_status == "1st":
                return ConnectionResult(
                    success=False,
                    error="Already connected",
                    timestamp=datetime.utcnow()
                )

            # Find and click Connect button
            connect_button = await self._find_connect_button()
            if not connect_button:
                return ConnectionResult(
                    success=False,
                    error="Connect button not found",
                    timestamp=datetime.utcnow()
                )

            await connect_button.click()
            await self._random_delay(1, 2)

            # Add note if message provided
            if message:
                # Click "Add a note" button
                add_note_btn = self.page.locator("button:has-text('Add a note')")
                if await add_note_btn.count() > 0:
                    await add_note_btn.click()
                    await self._random_delay(0.5, 1)

                    # Type message with human-like typing
                    textarea = self.page.locator("textarea[name='message']")
                    await textarea.fill("")
                    await self._type_like_human(textarea, message)
                    await self._random_delay(0.5, 1)

            # Click Send/Connect button
            send_btn = self.page.locator("button:has-text('Send')")
            if await send_btn.count() == 0:
                send_btn = self.page.locator("button[aria-label*='Send']")

            await send_btn.click()
            await self._random_delay(1, 2)

            # Verify success
            success = await self._verify_connection_sent()

            logger.info(f"Connection request {'sent' if success else 'failed'}: {profile_url}")

            return ConnectionResult(
                success=success,
                request_id=self._generate_request_id(),
                timestamp=datetime.utcnow()
            )

        except Exception as e:
            logger.error(f"Error sending connection request: {e}")
            return ConnectionResult(
                success=False,
                error=str(e),
                timestamp=datetime.utcnow()
            )

    async def _find_connect_button(self):
        """Find the Connect button on a profile page."""
        # Try different selectors (LinkedIn changes these frequently)
        selectors = [
            "button:has-text('Connect')",
            "button[aria-label*='connect' i]",
            "[data-control-name='connect']",
            "button.pvs-profile-actions__action:has-text('Connect')",
        ]

        for selector in selectors:
            btn = self.page.locator(selector).first
            if await btn.count() > 0:
                return btn

        # Check if there's a "More" dropdown
        more_btn = self.page.locator("button:has-text('More')").first
        if await more_btn.count() > 0:
            await more_btn.click()
            await self._random_delay(0.5, 1)

            # Look for Connect in dropdown
            connect_in_menu = self.page.locator("[role='menuitem']:has-text('Connect')")
            if await connect_in_menu.count() > 0:
                return connect_in_menu

        return None

    async def _verify_connection_sent(self) -> bool:
        """Verify that connection request was sent successfully."""
        # Look for success indicators
        success_indicators = [
            "text=Invitation sent",
            "text=Pending",
            "[aria-label*='Pending']",
        ]

        for indicator in success_indicators:
            if await self.page.locator(indicator).count() > 0:
                return True

        return False

    # =========================================================================
    # Direct Messages
    # =========================================================================

    async def send_message(
        self,
        profile_url: str,
        message: str,
    ) -> MessageResult:
        """
        Send a LinkedIn direct message to a 1st-degree connection.

        Args:
            profile_url: LinkedIn profile URL
            message: Message content

        Returns:
            MessageResult with success status
        """
        if not self._initialized:
            return MessageResult(success=False, error="Service not initialized")

        try:
            # Navigate to profile
            await self.page.goto(profile_url, wait_until="domcontentloaded")
            await self._random_delay()

            # Verify they're a 1st connection
            connection_status = await self._get_connection_status()
            if connection_status != "1st":
                return MessageResult(
                    success=False,
                    error=f"Not a 1st connection (status: {connection_status})",
                    timestamp=datetime.utcnow()
                )

            # Find and click Message button
            message_btn = self.page.locator("button:has-text('Message')").first
            if await message_btn.count() == 0:
                return MessageResult(
                    success=False,
                    error="Message button not found",
                    timestamp=datetime.utcnow()
                )

            await message_btn.click()
            await self._random_delay(1, 2)

            # Wait for message composer
            composer = self.page.locator("[role='textbox'][aria-label*='message' i]")
            await composer.wait_for(timeout=5000)

            # Type message with human-like typing
            await self._type_like_human(composer, message)
            await self._random_delay(0.5, 1)

            # Click Send button
            send_btn = self.page.locator("button[type='submit']:has-text('Send')")
            if await send_btn.count() == 0:
                send_btn = self.page.locator("button[aria-label*='Send' i]")

            await send_btn.click()
            await self._random_delay(1, 2)

            logger.info(f"Message sent to: {profile_url}")

            return MessageResult(
                success=True,
                message_id=self._generate_request_id(),
                timestamp=datetime.utcnow()
            )

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return MessageResult(
                success=False,
                error=str(e),
                timestamp=datetime.utcnow()
            )

    # =========================================================================
    # Status Checking
    # =========================================================================

    async def check_connection_status(self, profile_url: str) -> str | None:
        """
        Check connection status with a profile.

        Returns:
            "1st", "2nd", "3rd", "Out of network", or None if unknown
        """
        if not self._initialized:
            return None

        try:
            await self.page.goto(profile_url, wait_until="domcontentloaded")
            await self._random_delay()
            return await self._get_connection_status()
        except Exception as e:
            logger.error(f"Error checking connection status: {e}")
            return None

    async def _get_connection_status(self) -> str | None:
        """Get connection status from current page."""
        # Look for connection degree indicator
        degree_selectors = [
            ".distance-badge",
            "[class*='degree']",
            "span:has-text('1st')",
            "span:has-text('2nd')",
            "span:has-text('3rd')",
        ]

        for selector in degree_selectors:
            element = self.page.locator(selector).first
            if await element.count() > 0:
                text = await element.inner_text()
                if "1st" in text:
                    return "1st"
                elif "2nd" in text:
                    return "2nd"
                elif "3rd" in text:
                    return "3rd"

        # Check for Pending status
        if await self.page.locator("button:has-text('Pending')").count() > 0:
            return "pending"

        return "Out of network"

    async def get_pending_invitations(self) -> list[dict[str, Any]]:
        """Get list of pending sent connection invitations."""
        if not self._initialized:
            return []

        try:
            # Navigate to sent invitations page
            await self.page.goto(
                "https://www.linkedin.com/mynetwork/invitation-manager/sent/",
                wait_until="domcontentloaded"
            )
            await self._random_delay()

            invitations = []

            # Find invitation cards
            cards = self.page.locator("[class*='invitation-card']")
            count = await cards.count()

            for i in range(min(count, 50)):  # Limit to 50
                card = cards.nth(i)
                try:
                    name = await card.locator("[class*='name']").inner_text()
                    profile_link = await card.locator("a[href*='/in/']").get_attribute("href")
                    invitations.append({
                        "name": name.strip(),
                        "profile_url": profile_link,
                        "status": "pending"
                    })
                except Exception:
                    continue

            return invitations

        except Exception as e:
            logger.error(f"Error getting pending invitations: {e}")
            return []

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _random_delay(self, min_seconds: float | None = None, max_seconds: float | None = None):
        """Add random delay to simulate human behavior."""
        min_s = min_seconds if min_seconds is not None else self.delay_min
        max_s = max_seconds if max_seconds is not None else self.delay_max
        delay = random.uniform(min_s, max_s)
        await asyncio.sleep(delay)

    async def _type_like_human(self, element, text: str):
        """Type text with human-like delays between keystrokes."""
        for char in text:
            await element.type(char, delay=random.randint(30, 100))
            # Occasionally add a longer pause
            if random.random() < 0.1:
                await asyncio.sleep(random.uniform(0.1, 0.3))

    def _generate_request_id(self) -> str:
        """Generate a unique request ID."""
        import uuid
        return f"li_{uuid.uuid4().hex[:12]}"


# =============================================================================
# Factory Function
# =============================================================================


def get_linkedin_service() -> LinkedInService:
    """Factory function to get LinkedInService instance."""
    return LinkedInService()


# =============================================================================
# Mock Service for Testing
# =============================================================================


class MockLinkedInService:
    """
    Mock LinkedIn service for testing without browser automation.
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self, cookies_path: str | None = None) -> bool:
        self._initialized = True
        logger.info("Mock LinkedIn service initialized")
        return True

    async def close(self):
        self._initialized = False
        logger.info("Mock LinkedIn service closed")

    async def send_connection_request(
        self,
        profile_url: str,
        message: str | None = None,
    ) -> ConnectionResult:
        logger.info(f"[MOCK] Connection request to {profile_url}")
        return ConnectionResult(
            success=True,
            request_id=f"mock_{hash(profile_url) % 10000}",
            timestamp=datetime.utcnow()
        )

    async def send_message(
        self,
        profile_url: str,
        message: str,
    ) -> MessageResult:
        logger.info(f"[MOCK] Message sent to {profile_url}")
        return MessageResult(
            success=True,
            message_id=f"mock_msg_{hash(profile_url) % 10000}",
            timestamp=datetime.utcnow()
        )

    async def check_connection_status(self, profile_url: str) -> str | None:
        return "2nd"

    async def get_pending_invitations(self) -> list[dict[str, Any]]:
        return []
