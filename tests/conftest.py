"""
Shared pytest fixtures for Outreach Automation tests.

Provides:
- Database session fixtures (async SQLite for testing)
- Mock services (email, LinkedIn, AI)
- Sample data factories
- API client fixtures
"""

import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Set test environment before importing app modules
os.environ["TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


# =============================================================================
# Event Loop Fixture
# =============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create an async engine for testing with SQLite."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Import models to register them with SQLAlchemy
    from api.database.models import Base
    from api.database.outreach_models import (
        DailyQuota,
        EngagementEvent,
        MessageTemplate,
        OutreachCampaign,
        OutreachMessage,
        Prospect,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create an async session for testing."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_campaign_data() -> dict:
    """Sample campaign creation data."""
    return {
        "name": "Test Campaign Q1",
        "description": "Test campaign for Q1 outreach",
        "channels": ["linkedin", "email"],
        "daily_linkedin_limit": 20,
        "daily_email_limit": 50,
    }


@pytest.fixture
def sample_prospect_data() -> dict:
    """Sample prospect creation data."""
    return {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "company": "Acme Corp",
        "title": "VP of Marketing",
        "industry": "Technology",
        "location": "San Francisco, CA",
    }


@pytest.fixture
def sample_prospect_with_personalization() -> dict:
    """Sample prospect with full personalization data."""
    return {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane.smith@techcorp.com",
        "linkedin_url": "https://linkedin.com/in/janesmith",
        "company": "TechCorp",
        "title": "CEO",
        "industry": "SaaS",
        "location": "New York, NY",
        "pain_points": [
            "Manual content moderation",
            "Scaling customer support",
            "Brand consistency",
        ],
        "metrics": {
            "revenue": "$5M ARR",
            "employees": "50",
            "growth_rate": "200% YoY",
        },
    }


@pytest.fixture
def sample_csv_content() -> str:
    """Sample CSV content for import testing."""
    return """first_name,last_name,email,linkedin_url,company,title,industry,location
John,Doe,john@example.com,https://linkedin.com/in/johndoe,Acme Corp,VP Marketing,Technology,San Francisco
Jane,Smith,jane@techcorp.com,https://linkedin.com/in/janesmith,TechCorp,CEO,SaaS,New York
Bob,Johnson,bob@startup.io,https://linkedin.com/in/bobjohnson,Startup Inc,CTO,Fintech,Austin
"""


@pytest.fixture
def sample_csv_with_errors() -> str:
    """Sample CSV with validation errors."""
    return """first_name,last_name,email,linkedin_url,company
John,Doe,invalid-email,https://linkedin.com/in/johndoe,Acme
,Smith,jane@example.com,https://linkedin.com/in/jane,Tech
Bob,Johnson,bob@startup.io,not-a-linkedin-url,Startup
Valid,User,valid@example.com,https://linkedin.com/in/validuser,Valid Co
"""


@pytest.fixture
def sample_brand_brief_content() -> str:
    """Sample brand brief markdown content."""
    return """# BRAND BRIEF: TechCorp (Technology)

## Company Overview

| **Field** | Details |
|-----------|---------|
| **Company Name** | TechCorp |
| **Industry** | SaaS / Technology |
| **Revenue** | $5M ARR |
| **Employees** | 50 |
| **Location** | New York, NY |

## Priority: TIER 2 (Score: 85/100)

## Key Pain Points

1. **Manual Content Moderation** - Spending 20+ hours/week on manual review
2. **Scaling Customer Support** - Growing pains with support volume
3. **Brand Consistency** - Maintaining voice across channels

## Key Opportunities

- AI-powered moderation could save $50K/year
- Potential for 3x productivity gains
- Strong tech-forward culture

## Decision Makers

| Role | Search Strategy | Priority |
|------|-----------------|----------|
| CEO | Direct outreach | HIGH |
| VP Engineering | LinkedIn connection | MEDIUM |
| Head of Content | Conference networking | MEDIUM |

## Messaging Strategy

**For CEO/Founders:**
> "Transform your content operations with AI that understands your brand voice."

**For Technical Leaders:**
> "Enterprise-grade AI moderation with 99.9% accuracy and full API integration."

**Competitive Angle:**
> "Unlike generic solutions, we train on YOUR content to match your exact standards."

## Talking Points

1. "I noticed TechCorp's impressive growth - how are you scaling content moderation?"
2. "Many SaaS companies at your stage struggle with brand consistency..."
3. "Our AI reduced review time by 80% for similar companies."

## Sample Outreach Email

Subject: "Quick question about TechCorp's content strategy"

Hi Jane,

I noticed TechCorp's impressive 200% growth - congratulations! At that scale,
many SaaS companies struggle with maintaining brand voice across channels.

We've helped similar companies reduce content review time by 80% while
improving consistency. Would a quick 15-min call be worth exploring?

Best,
[Name]
"""


# =============================================================================
# Brand Brief Fixtures
# =============================================================================


@pytest.fixture
def temp_brand_briefs_dir(sample_brand_brief_content) -> Generator[Path, None, None]:
    """Create temporary brand briefs directory with sample content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        briefs_dir = Path(tmpdir) / "brand-briefs"
        briefs_dir.mkdir()

        # Create subdirectory for industry
        tech_dir = briefs_dir / "technology"
        tech_dir.mkdir()

        # Write sample brief
        brief_path = tech_dir / "techcorp.md"
        brief_path.write_text(sample_brand_brief_content, encoding="utf-8")

        yield briefs_dir


# =============================================================================
# Mock Service Fixtures
# =============================================================================


@pytest.fixture
def mock_email_service():
    """Mock email service for testing."""
    mock = MagicMock()
    mock.send_email = AsyncMock(return_value={
        "success": True,
        "message_id": "test-msg-123",
        "timestamp": datetime.utcnow().isoformat(),
    })
    mock.validate_email = MagicMock(return_value=True)
    return mock


@pytest.fixture
def mock_linkedin_service():
    """Mock LinkedIn service for testing."""
    mock = MagicMock()
    mock.send_connection_request = AsyncMock(return_value={
        "success": True,
        "request_id": "li-req-123",
    })
    mock.send_message = AsyncMock(return_value={
        "success": True,
        "message_id": "li-msg-123",
    })
    mock.check_connection_status = AsyncMock(return_value="connected")
    return mock


@pytest.fixture
def mock_ai_client():
    """Mock AI client for testing."""
    mock = MagicMock()
    mock.generate_text = AsyncMock(return_value="Generated message content here.")
    mock.generate_json = AsyncMock(return_value={
        "message": "Personalized outreach message",
        "subject": "Quick question for you",
        "personalization_elements": ["company", "role", "pain_point"],
    })
    return mock


@pytest.fixture
def mock_rate_limiter():
    """Mock rate limiter for testing."""
    mock = MagicMock()
    mock.check_quota = AsyncMock(return_value=(True, 10))  # allowed, remaining
    mock.increment_usage = AsyncMock(return_value=1)
    mock.get_current_usage = AsyncMock(return_value=5)
    mock.get_quota_status = AsyncMock(return_value={
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "campaign_id": 1,
        "channels": {
            "linkedin_connection": {"used": 5, "limit": 20, "remaining": 15},
            "email": {"used": 10, "limit": 50, "remaining": 40},
        },
    })
    return mock


# =============================================================================
# Message Validation Fixtures
# =============================================================================


@pytest.fixture
def valid_connection_message() -> str:
    """Valid LinkedIn connection request (<200 chars)."""
    return (
        "Hi John, I noticed your work at Acme Corp on AI initiatives. "
        "I help companies like yours scale content operations. Worth connecting?"
    )


@pytest.fixture
def valid_email_message() -> str:
    """Valid cold email message (150-400 words)."""
    return """Hi John,

I noticed Acme Corp's impressive growth in the AI space - congratulations on the recent Series B!

At your scale, many companies struggle with maintaining brand consistency across
content channels while scaling their moderation efforts. I've worked with similar
companies who were spending 20+ hours weekly on manual review.

We've helped companies like TechCorp and InnovateCo reduce their content review
time by 80% while actually improving quality scores. Our AI learns your specific
brand voice and applies it consistently.

A few quick wins we typically see:
- 80% reduction in review time
- 99.9% accuracy on brand guidelines
- $50K+ annual savings on moderation costs

Would a quick 15-minute call be worth exploring how this could work for Acme?

I'm free Tuesday or Thursday afternoon if either works.

Best regards,
[Name]

P.S. Happy to share a case study from a company in your space if helpful.
"""


@pytest.fixture
def invalid_long_connection_message() -> str:
    """Invalid LinkedIn connection (>200 chars)."""
    return (
        "Hi John, I noticed your excellent work at Acme Corp in the AI space. "
        "Your team has been doing amazing things with machine learning and natural "
        "language processing. I'd love to connect and share how we've helped similar "
        "companies transform their content operations with AI-powered solutions. "
        "Would you be open to a quick chat sometime next week?"
    )


@pytest.fixture
def message_without_cta() -> str:
    """Message missing a call-to-action."""
    return (
        "Hi John, I noticed your work at Acme Corp. "
        "Your team has been doing great things in the AI space. "
        "We help companies with content operations."
    )


# =============================================================================
# Prospect Context Fixtures
# =============================================================================


@pytest.fixture
def prospect_context() -> dict:
    """Prospect context for personalization testing."""
    return {
        "first_name": "John",
        "company": "Acme Corp",
        "prospect_role": "VP of Marketing",
        "industry": "Technology",
        "pain_points": [
            "Manual content moderation",
            "Scaling customer support",
        ],
        "key_metrics": [
            "20+ hours weekly on review",
            "$50K potential savings",
        ],
    }


# =============================================================================
# API Client Fixtures (for integration tests)
# =============================================================================


@pytest_asyncio.fixture
async def test_client():
    """Create test client for API testing."""
    from httpx import AsyncClient, ASGITransport
    from api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def api_headers() -> dict:
    """Standard API headers for testing."""
    return {
        "Content-Type": "application/json",
        "X-API-Key": "test-api-key",
    }


# =============================================================================
# Database Model Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def sample_campaign(db_session) -> "OutreachCampaign":
    """Create a sample campaign in the database."""
    from api.database.outreach_models import OutreachCampaign

    campaign = OutreachCampaign(
        name="Test Campaign",
        description="Test campaign for unit tests",
        channels=["linkedin", "email"],
        daily_linkedin_limit=20,
        daily_email_limit=50,
        is_active=True,
    )
    db_session.add(campaign)
    await db_session.flush()
    await db_session.refresh(campaign)
    return campaign


@pytest_asyncio.fixture
async def sample_prospect(db_session, sample_campaign) -> "Prospect":
    """Create a sample prospect in the database."""
    from api.database.outreach_models import Prospect, ProspectStatus

    prospect = Prospect(
        campaign_id=sample_campaign.id,
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        linkedin_url="https://linkedin.com/in/johndoe",
        company="Acme Corp",
        title="VP Marketing",
        industry="Technology",
        status=ProspectStatus.NEW,
        personalization_data={
            "pain_points": ["Manual moderation", "Scaling issues"],
        },
    )
    db_session.add(prospect)
    await db_session.flush()
    await db_session.refresh(prospect)
    return prospect


@pytest_asyncio.fixture
async def sample_message(db_session, sample_prospect) -> "OutreachMessage":
    """Create a sample message in the database."""
    from api.database.outreach_models import (
        MessageStatus,
        MessageType,
        OutreachChannel,
        OutreachMessage,
    )

    message = OutreachMessage(
        prospect_id=sample_prospect.id,
        channel=OutreachChannel.LINKEDIN,
        message_type=MessageType.CONNECTION_REQUEST,
        content="Hi John, I'd love to connect!",
        status=MessageStatus.DRAFT,
    )
    db_session.add(message)
    await db_session.flush()
    await db_session.refresh(message)
    return message
