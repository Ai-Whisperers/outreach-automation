"""
Factory Boy factories for generating test data.

Provides consistent, randomized test data for:
- Campaigns
- Prospects
- Messages
- Templates
- Events
"""

import random
import string
from datetime import datetime, timedelta
from typing import Any

import factory
from factory import fuzzy


# =============================================================================
# Helper Functions
# =============================================================================


def random_string(length: int = 10) -> str:
    """Generate a random string."""
    return "".join(random.choices(string.ascii_lowercase, k=length))


def random_email() -> str:
    """Generate a random email address."""
    return f"{random_string(8)}@{random_string(6)}.com"


def random_linkedin_url() -> str:
    """Generate a random LinkedIn URL."""
    return f"https://linkedin.com/in/{random_string(12)}"


# =============================================================================
# Data Classes (for non-ORM testing)
# =============================================================================


class CampaignFactory(factory.Factory):
    """Factory for campaign data dictionaries."""

    class Meta:
        model = dict

    name = factory.LazyFunction(lambda: f"Campaign {random_string(5)}")
    description = factory.LazyFunction(
        lambda: f"Test campaign for {random_string(10)}"
    )
    channels = ["linkedin", "email"]
    daily_linkedin_limit = fuzzy.FuzzyInteger(10, 25)
    daily_email_limit = fuzzy.FuzzyInteger(30, 100)
    is_active = True


class ProspectFactory(factory.Factory):
    """Factory for prospect data dictionaries."""

    class Meta:
        model = dict

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.LazyFunction(random_email)
    linkedin_url = factory.LazyFunction(random_linkedin_url)
    company = factory.Faker("company")
    title = factory.LazyFunction(
        lambda: random.choice([
            "CEO", "CTO", "VP Marketing", "VP Sales", "Director of Operations",
            "Head of Growth", "CMO", "COO", "Founder", "Co-Founder",
        ])
    )
    industry = factory.LazyFunction(
        lambda: random.choice([
            "Technology", "SaaS", "Fintech", "Healthcare", "E-commerce",
            "Manufacturing", "Consulting", "Marketing", "Education",
        ])
    )
    location = factory.Faker("city")
    status = "new"


class ProspectWithPersonalizationFactory(ProspectFactory):
    """Factory for prospects with full personalization data."""

    pain_points = factory.LazyFunction(
        lambda: random.sample([
            "Manual content moderation",
            "Scaling customer support",
            "Brand consistency",
            "Content velocity",
            "Team productivity",
            "Quality control",
            "Cost reduction",
            "Time to market",
        ], k=3)
    )
    metrics = factory.LazyFunction(
        lambda: {
            "revenue": random.choice(["$1M", "$5M", "$10M", "$50M", "$100M"]),
            "employees": str(random.choice([10, 25, 50, 100, 200, 500])),
            "growth_rate": f"{random.randint(20, 300)}%",
        }
    )


class MessageFactory(factory.Factory):
    """Factory for message data dictionaries."""

    class Meta:
        model = dict

    channel = factory.LazyFunction(
        lambda: random.choice(["linkedin", "email"])
    )
    message_type = factory.LazyFunction(
        lambda: random.choice([
            "connection_request", "linkedin_message",
            "email_initial", "email_followup_1",
        ])
    )
    subject = factory.LazyFunction(
        lambda: f"Quick question about {random_string(8)}"
    )
    content = factory.LazyFunction(
        lambda: f"Hi, I noticed your work at {random_string(10)}. {random_string(50)}. Worth a quick chat?"
    )
    status = "draft"


class TemplateFactory(factory.Factory):
    """Factory for message template data dictionaries."""

    class Meta:
        model = dict

    name = factory.LazyFunction(lambda: f"Template {random_string(5)}")
    channel = factory.LazyFunction(
        lambda: random.choice(["linkedin", "email"])
    )
    message_type = "email_initial"
    language = "en"
    subject_template = "Quick question for {{first_name}}"
    content_template = """Hi {{first_name}},

I noticed {{company}}'s impressive growth. We help companies like yours
with {{pain_point}}.

Would a quick 15-min call be worth exploring?

Best,
[Name]
"""
    variant = factory.LazyFunction(lambda: random.choice(["A", "B"]))
    is_active = True


# =============================================================================
# Specialized Factories
# =============================================================================


class ConnectionRequestFactory(factory.Factory):
    """Factory for LinkedIn connection request messages."""

    class Meta:
        model = dict

    message = factory.LazyFunction(
        lambda: random.choice([
            "Hi {first_name}, I noticed your work at {company}. Would love to connect!",
            "Hey {first_name}, I help {industry} companies like {company} scale. Worth connecting?",
            "Hi {first_name}, your {role} work at {company} caught my attention. Let's connect!",
        ])
    )
    character_count = factory.LazyAttribute(lambda obj: len(obj.message))
    personalization_elements = ["first_name", "company"]
    validation_passed = True


class ColdEmailFactory(factory.Factory):
    """Factory for cold email messages."""

    class Meta:
        model = dict

    subject = factory.LazyFunction(
        lambda: random.choice([
            "Quick question about {company}",
            "Idea for {company}'s {pain_point}",
            "Re: {company} growth",
        ])
    )
    body = factory.LazyFunction(
        lambda: f"""Hi {{first_name}},

I noticed {{company}}'s impressive growth in {{industry}}.

At your scale, many companies struggle with {{pain_point}}. We've helped
similar companies reduce their workload by 80%.

Would a quick 15-min call be worth exploring?

Best,
[Name]

P.S. Happy to share a relevant case study.
"""
    )
    word_count = factory.LazyAttribute(lambda obj: len(obj.body.split()))
    personalization_score = fuzzy.FuzzyFloat(0.6, 1.0)
    personalization_elements = ["first_name", "company", "industry", "pain_point"]


# =============================================================================
# CSV Data Factory
# =============================================================================


def generate_csv_rows(count: int = 10) -> str:
    """Generate CSV content with multiple prospects."""
    header = "first_name,last_name,email,linkedin_url,company,title,industry,location"
    rows = [header]

    for _ in range(count):
        prospect = ProspectFactory()
        rows.append(
            f"{prospect['first_name']},{prospect['last_name']},"
            f"{prospect['email']},{prospect['linkedin_url']},"
            f"{prospect['company']},{prospect['title']},"
            f"{prospect['industry']},{prospect['location']}"
        )

    return "\n".join(rows)


def generate_csv_with_duplicates(count: int = 10, duplicate_count: int = 3) -> str:
    """Generate CSV content with some duplicate entries."""
    rows = generate_csv_rows(count).split("\n")

    # Duplicate some rows
    for _ in range(duplicate_count):
        idx = random.randint(1, len(rows) - 1)
        rows.append(rows[idx])

    return "\n".join(rows)


# =============================================================================
# Brand Brief Factory
# =============================================================================


def generate_brand_brief(
    company_name: str = "TestCorp",
    industry: str = "Technology",
    tier: int = 2,
    revenue: str = "$5M",
    employees: str = "50",
) -> str:
    """Generate brand brief markdown content."""
    return f"""# BRAND BRIEF: {company_name} ({industry})

## Company Overview

| **Field** | Details |
|-----------|---------|
| **Company Name** | {company_name} |
| **Industry** | {industry} |
| **Revenue** | {revenue} |
| **Employees** | {employees} |
| **Location** | San Francisco, CA |

## Priority: TIER {tier} (Score: {85 - (tier - 1) * 10}/100)

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

## Messaging Strategy

**For CEO/Founders:**
> "Transform your content operations with AI that understands your brand voice."

**For Technical Leaders:**
> "Enterprise-grade AI moderation with 99.9% accuracy and full API integration."

**Competitive Angle:**
> "Unlike generic solutions, we train on YOUR content to match your exact standards."

## Talking Points

1. "I noticed {company_name}'s impressive growth - how are you scaling content moderation?"
2. "Many {industry} companies at your stage struggle with brand consistency..."

## Sample Outreach Email

Subject: "Quick question about {company_name}'s content strategy"

Hi [Name],

I noticed {company_name}'s impressive growth. Would a quick 15-min call be worth exploring?

Best,
[Sender]
"""


# =============================================================================
# Event Factory
# =============================================================================


class EngagementEventFactory(factory.Factory):
    """Factory for engagement event data."""

    class Meta:
        model = dict

    event_type = factory.LazyFunction(
        lambda: random.choice([
            "open", "click", "reply", "connection_accepted",
            "bounce", "unsubscribe",
        ])
    )
    channel = factory.LazyFunction(
        lambda: random.choice(["linkedin", "email"])
    )
    occurred_at = factory.LazyFunction(
        lambda: datetime.utcnow() - timedelta(days=random.randint(0, 30))
    )
    metadata = factory.LazyFunction(
        lambda: {
            "ip": f"192.168.1.{random.randint(1, 255)}",
            "user_agent": "Mozilla/5.0 (test)",
        }
    )


# =============================================================================
# Batch Factories
# =============================================================================


def create_campaign_with_prospects(
    prospect_count: int = 10,
    with_personalization: bool = False,
) -> dict[str, Any]:
    """Create a campaign with multiple prospects."""
    campaign = CampaignFactory()

    factory_class = (
        ProspectWithPersonalizationFactory if with_personalization
        else ProspectFactory
    )

    prospects = [factory_class() for _ in range(prospect_count)]

    return {
        "campaign": campaign,
        "prospects": prospects,
    }


def create_prospect_with_messages(
    message_count: int = 3,
) -> dict[str, Any]:
    """Create a prospect with multiple messages."""
    prospect = ProspectWithPersonalizationFactory()
    messages = [MessageFactory() for _ in range(message_count)]

    return {
        "prospect": prospect,
        "messages": messages,
    }
