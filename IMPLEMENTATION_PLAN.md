# Email Outreach System - Implementation Plan

## Implementation Status: COMPLETED

**Last Updated:** 2024-11-27
**Status:** All core phases implemented

---

## What Was Built

### New Services Created
| Service | File | Description |
|---------|------|-------------|
| Webhook Processor | `services/webhook_processor.py` | Processes SendGrid events, updates DB |
| Reply Detection | `services/reply_detection_service.py` | Detects replies, pauses sequences |
| Sequence Service | `services/sequence_service.py` | Configurable email sequences |
| Scraper Import | `services/scraper_import_service.py` | Imports prospects from webscraper |
| Warmup Service | `services/warmup_service.py` | Domain warmup management |
| Deliverability | `services/deliverability_service.py` | Metrics and health monitoring |
| Email Validation | `services/email_validation_service.py` | Pre-send email validation |

### New API Routes Created
| Route | File | Description |
|-------|------|-------------|
| Webhooks | `routes/webhooks.py` | SendGrid event & inbound webhooks |
| Sequences | `routes/sequences.py` | Sequence management |
| Deliverability | `routes/deliverability.py` | Health, metrics, warmup, validation |
| Scraper Import | `routes/scraper_import.py` | Import from webscraper JSON |

### Database Migrations
| File | Description |
|------|-------------|
| `migrations/001_enhance_email_outreach.sql` | All schema changes for new features |

### Email Service Enhancements
- Added `send_batch_v2()` for true SendGrid batch API
- Up to 1000 emails per API call
- Personalization per recipient

---

## Executive Summary

This plan enhances the existing Outreach-Automation system to create a robust, scalable cold email outreach platform. It integrates the company-webscraper data, improves the email sequence system, and adds critical missing features.

---

## Current State Assessment

### What's Already Built (Strengths)
- SendGrid integration with tracking pixels
- Prospect database with 9-state lifecycle
- AI personalization agent (LangGraph-based)
- Basic sequence structure (Day 1, 4, 8, 14)
- Campaign and quota management
- Celery task queue for async operations

### Critical Gaps to Address
1. No reply detection to pause sequences
2. Batch sending is sequential (not true batch)
3. Webhook events don't update database
4. Sequence timing is hardcoded
5. No engagement-based follow-up logic
6. Scraper data not integrated into pipeline
7. No email warmup strategy
8. Missing deliverability monitoring

---

## Phase 1: Foundation Fixes (Priority: Critical)

### 1.1 Fix SendGrid Webhook Processing
**Location:** `api/services/email_service.py`

**Current Problem:** Webhooks log events but don't update prospect/message status

**Implementation:**
```
- Update OutreachMessage status on: delivered, opened, clicked, bounced, spam_report
- Update Prospect status on: reply detected, bounce, unsubscribe
- Create EngagementEvent records for all webhook events
- Add signature verification for webhook security
```

**Database Changes:**
```sql
-- Add to OutreachMessage
ALTER TABLE outreach_messages ADD COLUMN opened_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN clicked_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN bounced_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN bounce_type VARCHAR(50);

-- Add to Prospect
ALTER TABLE prospects ADD COLUMN email_status VARCHAR(50) DEFAULT 'valid';
-- Values: valid, bounced, complained, unsubscribed
```

**Files to Modify:**
- `api/services/email_service.py` - Enhance `process_webhook()`
- `api/database/outreach_models.py` - Add new columns
- `api/routes/outreach.py` - Webhook endpoint improvements

---

### 1.2 Implement Reply Detection & Sequence Pausing
**Location:** `api/services/reply_detection_service.py` (NEW)

**Approach:**
- Option A: SendGrid Inbound Parse (webhook for incoming emails)
- Option B: IMAP polling for reply-to inbox
- Recommended: Option A (real-time, no polling)

**Implementation:**
```
1. Configure SendGrid Inbound Parse for reply-to domain
2. Create webhook endpoint: POST /webhooks/inbound-email
3. Parse incoming email, match to prospect by email address
4. Update prospect status to "replied"
5. Cancel all scheduled follow-ups for that prospect
6. Create engagement event with reply content
7. Notify campaign owner (optional Slack/email alert)
```

**New Files:**
- `api/services/reply_detection_service.py`
- `api/routes/webhooks.py` (consolidate all webhooks)

**Sequence Pause Logic:**
```python
async def handle_reply(prospect_id: int, reply_content: str):
    # 1. Update prospect status
    await prospect_repo.update_status(prospect_id, ProspectStatus.REPLIED)

    # 2. Cancel pending messages
    await message_repo.cancel_scheduled_messages(prospect_id)

    # 3. Log engagement
    await engagement_repo.create(
        prospect_id=prospect_id,
        event_type="reply",
        metadata={"content_preview": reply_content[:500]}
    )

    # 4. Trigger notification
    await notify_campaign_owner(prospect_id)
```

---

### 1.3 True Batch Sending with SendGrid
**Location:** `api/services/email_service.py`

**Current Problem:** Sends emails in a loop (sequential)

**Implementation:**
```python
async def send_batch_v2(self, messages: list[EmailMessage]) -> BatchResult:
    """
    Use SendGrid's /mail/send with personalizations array
    - Up to 1000 recipients per API call
    - Single API call, multiple personalized emails
    - Proper rate limiting (100 calls/second)
    """
    personalizations = []
    for msg in messages:
        personalizations.append({
            "to": [{"email": msg.to_email, "name": msg.to_name}],
            "subject": msg.subject,
            "substitutions": msg.merge_fields
        })

    # SendGrid batch API call
    # Track message IDs for each recipient
```

**Benefits:**
- 10x faster sending
- Lower API costs
- Atomic operation (all or none)

---

## Phase 2: Scraper Integration Pipeline

### 2.1 Scraper-to-Prospect Import Pipeline
**Location:** `api/services/scraper_import_service.py` (NEW)

**Data Flow:**
```
company-webscraper/output/*.json
    → Parse & Extract
    → Enrich Prospect Records
    → Generate Personalization Context
    → Store in Database
```

**Key Data Mappings:**

| Scraper Field | Prospect Field | Usage |
|---------------|----------------|-------|
| `decision_makers[].email` | `email` | Primary contact |
| `decision_makers[].name` | `first_name`, `last_name` | Personalization |
| `decision_makers[].title` | `title` | Role-based messaging |
| `decision_makers[].linkedin` | `linkedin_url` | Research link |
| `company.name` | `company` | Company reference |
| `company.industry` | `industry` | Industry templates |
| `company.headquarters` | `location` | Geo targeting |
| `sentiment.top_complaints` | `personalization_data.pain_points` | Pain point hooks |
| `sentiment.emotion_analysis` | `personalization_data.sentiment` | Tone adjustment |
| `scoring.tier` | `personalization_data.priority` | Sequence selection |
| `outreach_materials.talking_points` | `personalization_data.hooks` | Email hooks |
| `competitor_analysis` | `personalization_data.competitors` | Differentiation |

**Implementation:**
```python
class ScraperImportService:
    async def import_from_scraper_output(self, json_path: Path) -> ImportResult:
        data = load_json(json_path)

        # Extract decision makers as prospects
        prospects = []
        for dm in data.get("decision_makers", []):
            prospect = ProspectCreate(
                email=dm["email"],
                first_name=dm["name"].split()[0],
                last_name=" ".join(dm["name"].split()[1:]),
                title=dm["title"],
                company=data["company"]["name"],
                industry=data["company"]["industry"],
                location=dm.get("location", data["company"]["headquarters"]),
                personalization_data={
                    "pain_points": self._extract_pain_points(data),
                    "talking_points": data["outreach_materials"]["talking_points"],
                    "competitors": [c["name"] for c in data["competitors"]],
                    "recent_news": data["news"]["recent"][:3],
                    "sentiment_score": data["sentiment"]["overall"],
                    "priority_tier": data["scoring"]["tier"],
                    "company_size": data["employees"]["global_count"],
                    "tech_stack": data["website"]["tech_stack"],
                }
            )
            prospects.append(prospect)

        return await self.prospect_service.bulk_create(prospects)

    def _extract_pain_points(self, data: dict) -> list[str]:
        """Convert sentiment complaints to actionable pain points"""
        complaints = data.get("sentiment", {}).get("top_complaints", [])
        return [
            f"{c['category']}: {c['description']}"
            for c in complaints[:5]
        ]
```

**New Endpoint:**
```
POST /prospects/import/scraper
Body: { "scraper_output_path": "path/to/output.json" }
      OR
      { "scraper_output_dir": "path/to/output/" }  # Batch import
```

---

### 2.2 Enhanced Personalization Engine
**Location:** `api/agents/personalization_agent.py`

**Current State:** Uses brand brief data only

**Enhancement:** Incorporate scraper data for deeper personalization

**New Personalization Signals:**
```python
PERSONALIZATION_SIGNALS = {
    # From Scraper
    "pain_points": "Direct address of known complaints",
    "recent_news": "Timely reference to company events",
    "competitors": "Competitive positioning",
    "tech_stack": "Integration opportunity mention",
    "hiring_signals": "Growth/expansion acknowledgment",
    "sentiment_trend": "Tone adjustment based on company mood",

    # Computed
    "company_size_tier": "SMB vs Enterprise messaging",
    "digital_maturity": "Sophistication of pitch",
    "urgency_score": "Call-to-action strength"
}
```

**Enhanced Prompt Template:**
```python
PERSONALIZATION_PROMPT = """
You are writing a cold email to {first_name} at {company}.

PROSPECT CONTEXT:
- Role: {title}
- Company Size: {company_size} employees
- Industry: {industry}
- Priority Tier: {priority_tier}

INTELLIGENCE FROM RESEARCH:
- Known Pain Points: {pain_points}
- Recent News: {recent_news}
- Competitors They Face: {competitors}
- Current Tech Stack: {tech_stack}
- Customer Sentiment: {sentiment_summary}

TALKING POINTS TO INCORPORATE:
{talking_points}

CONSTRAINTS:
- Subject line: Max 50 chars, curiosity-driven
- Body: 50-125 words
- Must include ONE specific pain point reference
- Must include ONE personalized hook (news/competitor/metric)
- End with soft CTA (question, not demand)
- Tone: {tone_based_on_tier}

Generate the email:
"""
```

---

### 2.3 Automated Scraper → Outreach Pipeline
**Location:** `api/tasks/scraper_tasks.py` (NEW)

**Workflow:**
```
1. File watcher monitors company-webscraper/output/
2. New JSON detected → Trigger import task
3. Import creates prospects with enriched data
4. Auto-assign to campaign based on tier/industry
5. Generate personalized messages
6. Schedule according to campaign sequence
```

**Implementation:**
```python
# Celery task
@celery_app.task
def process_new_scraper_output(file_path: str):
    """
    Triggered when new scraper output is detected
    """
    # 1. Import prospects
    import_result = scraper_import_service.import_from_scraper_output(file_path)

    # 2. Auto-assign campaign
    for prospect in import_result.prospects:
        campaign = campaign_matcher.find_best_campaign(
            industry=prospect.industry,
            tier=prospect.personalization_data["priority_tier"]
        )
        prospect.campaign_id = campaign.id

    # 3. Generate messages
    for prospect in import_result.prospects:
        message_generator.generate_sequence(prospect)

    # 4. Schedule first email
    for prospect in import_result.prospects:
        scheduler.schedule_initial_email(prospect)
```

---

## Phase 3: Email Sequence System

### 3.1 Configurable Sequence Engine
**Location:** `api/services/sequence_service.py` (NEW)

**Current Problem:** Hardcoded Day 1, 4, 8, 14 timing

**New Sequence Configuration:**
```python
class SequenceConfig(BaseModel):
    name: str
    steps: list[SequenceStep]

class SequenceStep(BaseModel):
    step_number: int
    delay_days: int  # Days after previous step
    delay_hours: int = 0  # Fine-grained timing
    message_type: MessageType
    template_id: Optional[str]  # Use specific template or generate
    conditions: Optional[StepConditions]  # Skip conditions

class StepConditions(BaseModel):
    skip_if_opened: bool = False
    skip_if_clicked: bool = False
    require_no_reply: bool = True  # Always true for follow-ups
```

**Example Sequences:**
```python
# Aggressive (High Priority Prospects)
AGGRESSIVE_SEQUENCE = SequenceConfig(
    name="aggressive",
    steps=[
        SequenceStep(step_number=1, delay_days=0, message_type=MessageType.EMAIL_INITIAL),
        SequenceStep(step_number=2, delay_days=2, message_type=MessageType.EMAIL_FOLLOWUP_1),
        SequenceStep(step_number=3, delay_days=3, message_type=MessageType.EMAIL_FOLLOWUP_2),
        SequenceStep(step_number=4, delay_days=4, message_type=MessageType.EMAIL_FOLLOWUP_3),
        SequenceStep(step_number=5, delay_days=5, message_type=MessageType.EMAIL_FOLLOWUP_4),
    ]
)

# Standard (Medium Priority)
STANDARD_SEQUENCE = SequenceConfig(
    name="standard",
    steps=[
        SequenceStep(step_number=1, delay_days=0, message_type=MessageType.EMAIL_INITIAL),
        SequenceStep(step_number=2, delay_days=3, message_type=MessageType.EMAIL_FOLLOWUP_1),
        SequenceStep(step_number=3, delay_days=5, message_type=MessageType.EMAIL_FOLLOWUP_2),
        SequenceStep(step_number=4, delay_days=7, message_type=MessageType.EMAIL_FOLLOWUP_3),
        SequenceStep(step_number=5, delay_days=10, message_type=MessageType.EMAIL_FOLLOWUP_4),
    ]
)

# Gentle (Lower Priority / Nurture)
GENTLE_SEQUENCE = SequenceConfig(
    name="gentle",
    steps=[
        SequenceStep(step_number=1, delay_days=0, message_type=MessageType.EMAIL_INITIAL),
        SequenceStep(step_number=2, delay_days=7, message_type=MessageType.EMAIL_FOLLOWUP_1),
        SequenceStep(step_number=3, delay_days=14, message_type=MessageType.EMAIL_FOLLOWUP_2),
        SequenceStep(step_number=4, delay_days=21, message_type=MessageType.EMAIL_FOLLOWUP_3),
    ]
)
```

**Database Changes:**
```sql
-- New table for sequence definitions
CREATE TABLE sequences (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) UNIQUE,
    description TEXT,
    steps JSONB,  -- Array of SequenceStep
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Link campaigns to sequences
ALTER TABLE outreach_campaigns ADD COLUMN sequence_id INTEGER REFERENCES sequences(id);

-- Track prospect's position in sequence
ALTER TABLE prospects ADD COLUMN current_sequence_step INTEGER DEFAULT 0;
ALTER TABLE prospects ADD COLUMN sequence_paused BOOLEAN DEFAULT FALSE;
ALTER TABLE prospects ADD COLUMN sequence_paused_reason VARCHAR(100);
```

---

### 3.2 Engagement-Based Follow-up Logic
**Location:** `api/services/sequence_service.py`

**Smart Follow-up Rules:**
```python
class FollowUpEngine:
    async def should_send_followup(self, prospect: Prospect, step: SequenceStep) -> Decision:
        # Check reply (always blocks)
        if await self.has_replied(prospect):
            return Decision(send=False, reason="prospect_replied")

        # Check bounce
        if prospect.email_status == "bounced":
            return Decision(send=False, reason="email_bounced")

        # Check unsubscribe
        if prospect.email_status == "unsubscribed":
            return Decision(send=False, reason="unsubscribed")

        # Engagement-based logic
        engagement = await self.get_engagement_summary(prospect)

        # High engagement: might want to slow down (they're reading)
        if engagement.open_rate > 0.8 and engagement.click_rate > 0.3:
            # They're engaged but not replying - adjust message
            return Decision(
                send=True,
                adjust_tone="more_direct_cta",
                reason="high_engagement_no_reply"
            )

        # No engagement: might want different subject lines
        if engagement.open_rate == 0 and step.step_number > 2:
            return Decision(
                send=True,
                adjust_tone="different_angle",
                reason="no_opens_try_new_approach"
            )

        return Decision(send=True, reason="standard_followup")
```

---

### 3.3 Follow-up Message Variation
**Location:** `api/agents/personalization_agent.py`

**Problem:** Follow-ups shouldn't repeat the same pitch

**Follow-up Strategy:**
```python
FOLLOWUP_STRATEGIES = {
    1: {
        "angle": "gentle_reminder",
        "tone": "casual",
        "hook": "reference_previous_email",
        "length": "shorter",
        "cta": "soft_question"
    },
    2: {
        "angle": "new_value_prop",
        "tone": "helpful",
        "hook": "share_resource_or_insight",
        "length": "medium",
        "cta": "offer_value"
    },
    3: {
        "angle": "social_proof",
        "tone": "confident",
        "hook": "case_study_or_result",
        "length": "short",
        "cta": "specific_ask"
    },
    4: {
        "angle": "breakup",
        "tone": "respectful",
        "hook": "acknowledge_busy",
        "length": "very_short",
        "cta": "close_loop"
    }
}
```

**Generation Prompt Adjustment:**
```python
def get_followup_prompt(step_number: int, previous_emails: list, engagement: dict):
    strategy = FOLLOWUP_STRATEGIES[step_number]

    return f"""
    This is follow-up #{step_number} in a sequence.

    PREVIOUS EMAILS SENT:
    {format_previous_emails(previous_emails)}

    ENGAGEMENT SO FAR:
    - Opens: {engagement['opens']}
    - Clicks: {engagement['clicks']}
    - Last opened: {engagement['last_open']}

    STRATEGY FOR THIS EMAIL:
    - Angle: {strategy['angle']}
    - Tone: {strategy['tone']}
    - Hook type: {strategy['hook']}
    - Length: {strategy['length']}
    - CTA style: {strategy['cta']}

    IMPORTANT:
    - Do NOT repeat points from previous emails
    - Reference that you've reached out before (briefly)
    - {get_strategy_specific_instructions(strategy)}

    Generate the follow-up email:
    """
```

---

## Phase 4: Deliverability & Warmup

### 4.1 Domain Warmup System
**Location:** `api/services/warmup_service.py` (NEW)

**Why It Matters:** New domains/IPs sending 100s of emails immediately = spam folder

**Warmup Schedule:**
```python
WARMUP_SCHEDULE = {
    # Week: (daily_limit, recommended_delay_between_emails_seconds)
    1: (20, 300),    # 20/day, 5 min apart
    2: (40, 180),    # 40/day, 3 min apart
    3: (70, 120),    # 70/day, 2 min apart
    4: (100, 60),    # 100/day, 1 min apart
    5: (150, 45),
    6: (200, 30),
    7: (300, 20),
    8: (500, 15),    # Full capacity
}

class WarmupService:
    async def get_daily_limit(self, domain: str) -> int:
        domain_age = await self.get_domain_age(domain)
        week = min(domain_age.days // 7, 8)
        return WARMUP_SCHEDULE.get(week, (500, 15))[0]

    async def get_send_delay(self, domain: str) -> int:
        domain_age = await self.get_domain_age(domain)
        week = min(domain_age.days // 7, 8)
        return WARMUP_SCHEDULE.get(week, (500, 15))[1]
```

**Database:**
```sql
CREATE TABLE domain_warmup (
    id INTEGER PRIMARY KEY,
    domain VARCHAR(255) UNIQUE,
    started_at TIMESTAMP,
    current_week INTEGER DEFAULT 1,
    total_sent INTEGER DEFAULT 0,
    bounce_rate FLOAT DEFAULT 0,
    spam_rate FLOAT DEFAULT 0,
    is_warmed BOOLEAN DEFAULT FALSE
);
```

---

### 4.2 Deliverability Monitoring
**Location:** `api/services/deliverability_service.py` (NEW)

**Key Metrics to Track:**
```python
class DeliverabilityMetrics(BaseModel):
    domain: str
    period: str  # "daily", "weekly", "monthly"

    # Core metrics
    total_sent: int
    delivered: int
    bounced: int
    spam_reports: int

    # Rates
    delivery_rate: float  # Target: > 95%
    bounce_rate: float    # Target: < 3%
    spam_rate: float      # Target: < 0.1%
    open_rate: float      # Benchmark: 15-25%
    click_rate: float     # Benchmark: 2-5%
    reply_rate: float     # Benchmark: 1-5%

    # Health indicators
    health_score: int     # 0-100
    alerts: list[str]     # Active warnings
```

**Alert Thresholds:**
```python
ALERT_THRESHOLDS = {
    "bounce_rate": {"warning": 0.03, "critical": 0.05},
    "spam_rate": {"warning": 0.001, "critical": 0.005},
    "delivery_rate": {"warning": 0.95, "critical": 0.90},
}

async def check_health(self, domain: str) -> HealthCheck:
    metrics = await self.get_metrics(domain, period="daily")
    alerts = []

    if metrics.bounce_rate > ALERT_THRESHOLDS["bounce_rate"]["critical"]:
        alerts.append(Alert(
            level="critical",
            message=f"Bounce rate {metrics.bounce_rate:.1%} exceeds 5%",
            action="Pause sending immediately. Clean email list."
        ))

    if metrics.spam_rate > ALERT_THRESHOLDS["spam_rate"]["warning"]:
        alerts.append(Alert(
            level="warning",
            message=f"Spam rate {metrics.spam_rate:.2%} is elevated",
            action="Review email content. Check unsubscribe link."
        ))

    return HealthCheck(
        domain=domain,
        health_score=self._calculate_score(metrics),
        alerts=alerts,
        recommendation=self._get_recommendation(metrics)
    )
```

---

### 4.3 Email Validation Pipeline
**Location:** `api/services/email_validation_service.py` (NEW)

**Pre-send Validation:**
```python
class EmailValidationService:
    async def validate_before_send(self, email: str) -> ValidationResult:
        checks = await asyncio.gather(
            self.check_format(email),
            self.check_mx_record(email),
            self.check_disposable(email),
            self.check_role_based(email),  # info@, support@, etc.
            self.check_catch_all(email),
        )

        return ValidationResult(
            email=email,
            is_valid=all(c.passed for c in checks),
            checks=checks,
            risk_score=self._calculate_risk(checks)
        )

    async def check_mx_record(self, email: str) -> Check:
        """Verify domain can receive email"""
        domain = email.split("@")[1]
        try:
            mx_records = await dns.resolver.resolve(domain, 'MX')
            return Check(name="mx_record", passed=True)
        except:
            return Check(name="mx_record", passed=False, reason="No MX record")

    async def check_disposable(self, email: str) -> Check:
        """Check against disposable email domain list"""
        domain = email.split("@")[1]
        is_disposable = domain in DISPOSABLE_DOMAINS
        return Check(
            name="disposable",
            passed=not is_disposable,
            reason="Disposable email domain" if is_disposable else None
        )
```

**Integration with Prospect Import:**
```python
async def import_prospects(self, prospects: list[ProspectCreate]):
    validated = []
    for p in prospects:
        result = await email_validator.validate_before_send(p.email)
        if result.is_valid:
            validated.append(p)
        else:
            logger.warning(f"Invalid email skipped: {p.email} - {result.reason}")
            # Optionally store in quarantine table for review

    return await self.bulk_create(validated)
```

---

## Phase 5: Analytics & Optimization

### 5.1 Campaign Analytics Dashboard
**Location:** `api/services/analytics_service.py` (enhance existing)

**New Metrics:**
```python
class CampaignAnalytics(BaseModel):
    campaign_id: int
    period: str

    # Volume
    prospects_total: int
    prospects_contacted: int
    messages_sent: int

    # Engagement funnel
    delivered: int
    opened: int
    clicked: int
    replied: int
    meetings_booked: int  # Manual tracking or calendar integration

    # Rates
    delivery_rate: float
    open_rate: float
    click_rate: float
    reply_rate: float
    meeting_rate: float

    # Sequence performance
    avg_touches_to_reply: float
    best_performing_step: int
    dropout_by_step: dict[int, int]

    # Content performance
    best_subject_lines: list[SubjectLinePerformance]
    best_cta_types: list[CTAPerformance]

    # Timing
    best_send_day: str
    best_send_hour: int
    avg_time_to_open: timedelta
    avg_time_to_reply: timedelta
```

**Funnel Visualization Data:**
```python
async def get_funnel(self, campaign_id: int) -> Funnel:
    return Funnel(
        stages=[
            FunnelStage(name="Prospects", count=1000, rate=1.0),
            FunnelStage(name="Contacted", count=950, rate=0.95),
            FunnelStage(name="Delivered", count=920, rate=0.92),
            FunnelStage(name="Opened", count=230, rate=0.23),
            FunnelStage(name="Clicked", count=45, rate=0.045),
            FunnelStage(name="Replied", count=28, rate=0.028),
            FunnelStage(name="Meeting", count=8, rate=0.008),
        ]
    )
```

---

### 5.2 A/B Testing Framework
**Location:** `api/services/ab_testing_service.py` (NEW)

**Test Types:**
```python
class ABTest(BaseModel):
    id: int
    campaign_id: int
    test_type: TestType  # subject_line, body, cta, send_time
    variants: list[Variant]
    traffic_split: list[float]  # [0.5, 0.5] for 50/50
    min_sample_size: int
    confidence_level: float = 0.95
    status: TestStatus  # running, concluded, cancelled
    winner: Optional[str]

class Variant(BaseModel):
    id: str  # "A", "B", "C"
    content: str  # The actual subject/body/CTA
    sent: int = 0
    opened: int = 0
    clicked: int = 0
    replied: int = 0
```

**Statistical Significance:**
```python
from scipy import stats

def calculate_significance(variant_a: Variant, variant_b: Variant, metric: str) -> TestResult:
    """Calculate if difference is statistically significant"""

    # Get success/failure counts
    a_success = getattr(variant_a, metric)
    a_total = variant_a.sent
    b_success = getattr(variant_b, metric)
    b_total = variant_b.sent

    # Chi-square test
    contingency_table = [
        [a_success, a_total - a_success],
        [b_success, b_total - b_success]
    ]
    chi2, p_value, dof, expected = stats.chi2_contingency(contingency_table)

    # Determine winner
    a_rate = a_success / a_total if a_total > 0 else 0
    b_rate = b_success / b_total if b_total > 0 else 0

    return TestResult(
        is_significant=p_value < 0.05,
        p_value=p_value,
        winner="A" if a_rate > b_rate else "B",
        lift=abs(a_rate - b_rate) / min(a_rate, b_rate) if min(a_rate, b_rate) > 0 else 0
    )
```

---

### 5.3 Smart Send Time Optimization
**Location:** `api/services/send_time_optimizer.py` (NEW)

**Approach:**
```python
class SendTimeOptimizer:
    async def get_optimal_time(self, prospect: Prospect) -> datetime:
        """
        Determine best send time based on:
        1. Prospect's timezone (from location)
        2. Historical engagement data for similar prospects
        3. Industry benchmarks
        """

        # Get prospect timezone
        tz = await self.get_timezone(prospect.location)

        # Get historical best times for this segment
        segment_data = await self.get_segment_engagement(
            industry=prospect.industry,
            title_level=self.get_seniority(prospect.title)
        )

        # Default to Tuesday-Thursday, 9-11 AM local
        if not segment_data:
            return self._default_time(tz)

        return self._best_time_from_data(segment_data, tz)

    def _default_time(self, tz: timezone) -> datetime:
        """B2B defaults: Tue-Thu, 9-11 AM"""
        now = datetime.now(tz)

        # Find next Tuesday, Wednesday, or Thursday
        days_ahead = {
            0: 1,  # Monday -> Tuesday
            1: 0,  # Tuesday -> Tuesday
            2: 0,  # Wednesday -> Wednesday
            3: 0,  # Thursday -> Thursday
            4: 4,  # Friday -> Tuesday
            5: 3,  # Saturday -> Tuesday
            6: 2,  # Sunday -> Tuesday
        }

        target_day = now + timedelta(days=days_ahead[now.weekday()])
        target_time = target_day.replace(hour=10, minute=0, second=0)

        # Add some randomization (9:00-11:00)
        random_minutes = random.randint(0, 120)
        return target_time + timedelta(minutes=random_minutes)
```

---

## Phase 6: API Endpoints Summary

### New Endpoints to Create

```yaml
# Webhooks
POST /webhooks/sendgrid          # SendGrid event webhooks
POST /webhooks/inbound-email     # Reply detection (SendGrid Inbound Parse)

# Scraper Integration
POST /prospects/import/scraper   # Import from scraper JSON
POST /prospects/import/scraper/batch  # Import entire output directory

# Sequences
GET    /sequences                # List all sequences
POST   /sequences                # Create custom sequence
GET    /sequences/{id}           # Get sequence details
PUT    /sequences/{id}           # Update sequence
DELETE /sequences/{id}           # Delete sequence

# Deliverability
GET /deliverability/health       # Overall health check
GET /deliverability/metrics      # Detailed metrics
GET /deliverability/warmup       # Warmup status

# A/B Testing
POST   /ab-tests                 # Create new test
GET    /ab-tests/{id}            # Get test status/results
POST   /ab-tests/{id}/conclude   # Manually conclude test
DELETE /ab-tests/{id}            # Cancel test

# Analytics (enhanced)
GET /analytics/funnel/{campaign_id}     # Funnel visualization
GET /analytics/timing/{campaign_id}     # Send time analysis
GET /analytics/content/{campaign_id}    # Content performance
```

---

## Phase 7: Database Migrations

### Migration Script
```sql
-- Migration: 001_enhance_email_outreach.sql

-- 1. Enhance OutreachMessage
ALTER TABLE outreach_messages ADD COLUMN opened_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN clicked_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN bounced_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN bounce_type VARCHAR(50);

-- 2. Enhance Prospect
ALTER TABLE prospects ADD COLUMN email_status VARCHAR(50) DEFAULT 'valid';
ALTER TABLE prospects ADD COLUMN current_sequence_step INTEGER DEFAULT 0;
ALTER TABLE prospects ADD COLUMN sequence_paused BOOLEAN DEFAULT FALSE;
ALTER TABLE prospects ADD COLUMN sequence_paused_reason VARCHAR(100);

-- 3. Sequences table
CREATE TABLE sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    steps JSON NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Link campaigns to sequences
ALTER TABLE outreach_campaigns ADD COLUMN sequence_id INTEGER REFERENCES sequences(id);

-- 5. Domain warmup tracking
CREATE TABLE domain_warmup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain VARCHAR(255) UNIQUE NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_week INTEGER DEFAULT 1,
    total_sent INTEGER DEFAULT 0,
    bounce_rate FLOAT DEFAULT 0,
    spam_rate FLOAT DEFAULT 0,
    is_warmed BOOLEAN DEFAULT FALSE
);

-- 6. Deliverability metrics (daily snapshots)
CREATE TABLE deliverability_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    sent INTEGER DEFAULT 0,
    delivered INTEGER DEFAULT 0,
    bounced INTEGER DEFAULT 0,
    spam_reports INTEGER DEFAULT 0,
    opens INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    UNIQUE(domain, date)
);

-- 7. A/B Tests
CREATE TABLE ab_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES outreach_campaigns(id),
    test_type VARCHAR(50) NOT NULL,
    variants JSON NOT NULL,
    traffic_split JSON NOT NULL,
    min_sample_size INTEGER DEFAULT 100,
    confidence_level FLOAT DEFAULT 0.95,
    status VARCHAR(50) DEFAULT 'running',
    winner VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    concluded_at TIMESTAMP
);

-- 8. Indexes
CREATE INDEX ix_deliverability_domain_date ON deliverability_metrics(domain, date);
CREATE INDEX ix_ab_tests_campaign ON ab_tests(campaign_id);
CREATE INDEX ix_prospects_sequence ON prospects(campaign_id, current_sequence_step);
```

---

## Implementation Order

### Week 1-2: Foundation
1. [ ] SendGrid webhook processing (1.1)
2. [ ] Reply detection & sequence pausing (1.2)
3. [ ] Database migrations
4. [ ] True batch sending (1.3)

### Week 3-4: Scraper Integration
5. [ ] Scraper import service (2.1)
6. [ ] Enhanced personalization with scraper data (2.2)
7. [ ] Automated pipeline (2.3)

### Week 5-6: Sequences
8. [ ] Configurable sequence engine (3.1)
9. [ ] Engagement-based follow-up logic (3.2)
10. [ ] Follow-up message variation (3.3)

### Week 7-8: Deliverability
11. [ ] Domain warmup system (4.1)
12. [ ] Deliverability monitoring (4.2)
13. [ ] Email validation pipeline (4.3)

### Week 9-10: Analytics
14. [ ] Enhanced analytics dashboard (5.1)
15. [ ] A/B testing framework (5.2)
16. [ ] Send time optimization (5.3)

---

## File Structure (New Files)

```
api/
├── services/
│   ├── scraper_import_service.py      # NEW
│   ├── reply_detection_service.py     # NEW
│   ├── sequence_service.py            # NEW
│   ├── warmup_service.py              # NEW
│   ├── deliverability_service.py      # NEW
│   ├── email_validation_service.py    # NEW
│   ├── ab_testing_service.py          # NEW
│   ├── send_time_optimizer.py         # NEW
│   └── email_service.py               # MODIFY
│
├── routes/
│   ├── webhooks.py                    # NEW
│   ├── sequences.py                   # NEW
│   ├── deliverability.py              # NEW
│   ├── ab_tests.py                    # NEW
│   └── prospects.py                   # MODIFY
│
├── tasks/
│   ├── scraper_tasks.py               # NEW
│   └── outreach_tasks.py              # MODIFY
│
├── database/
│   ├── outreach_models.py             # MODIFY
│   └── migrations/
│       └── 001_enhance_email_outreach.sql  # NEW
│
└── models/
    ├── sequence_models.py             # NEW
    ├── deliverability_models.py       # NEW
    └── ab_test_models.py              # NEW
```

---

## Success Metrics

After implementation, track these KPIs:

| Metric | Target | Current Baseline |
|--------|--------|------------------|
| Delivery Rate | > 95% | TBD |
| Open Rate | > 20% | TBD |
| Reply Rate | > 3% | TBD |
| Bounce Rate | < 2% | TBD |
| Spam Rate | < 0.1% | TBD |
| Avg Touches to Reply | < 3 | TBD |
| Time to First Reply | < 5 days | TBD |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| SendGrid account suspension | Warmup properly, monitor bounce/spam rates |
| Low deliverability | Validate emails before sending, use dedicated IP |
| Prospect complaints | Easy unsubscribe, respect opt-outs immediately |
| Data quality issues | Validate scraper output, quarantine suspicious emails |
| Over-personalization (creepy) | A/B test personalization depth, get feedback |

---

## Next Steps

1. Review this plan and approve/modify priorities
2. Set up Alembic for database migrations (if not already)
3. Begin Phase 1 implementation
4. Set up staging environment for testing
5. Create test prospects for validation

---

*Plan created: 2024*
*Status: Awaiting approval*
