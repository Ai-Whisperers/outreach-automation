-- Migration: 001_enhance_email_outreach.sql
-- Description: Enhance email outreach system with sequences, deliverability, and scraper integration
-- Date: 2024-11-27

-- =============================================================================
-- 1. Enhance OutreachMessage table
-- =============================================================================

ALTER TABLE outreach_messages ADD COLUMN opened_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN clicked_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN bounced_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN bounce_type VARCHAR(50);
ALTER TABLE outreach_messages ADD COLUMN delivered_at TIMESTAMP;
ALTER TABLE outreach_messages ADD COLUMN open_count INTEGER DEFAULT 0;
ALTER TABLE outreach_messages ADD COLUMN click_count INTEGER DEFAULT 0;

-- =============================================================================
-- 2. Enhance Prospect table
-- =============================================================================

ALTER TABLE prospects ADD COLUMN email_status VARCHAR(50) DEFAULT 'valid';
-- Values: valid, bounced, complained, unsubscribed

ALTER TABLE prospects ADD COLUMN current_sequence_step INTEGER DEFAULT 0;
ALTER TABLE prospects ADD COLUMN sequence_paused BOOLEAN DEFAULT FALSE;
ALTER TABLE prospects ADD COLUMN sequence_paused_reason VARCHAR(100);
ALTER TABLE prospects ADD COLUMN sequence_started_at TIMESTAMP;
ALTER TABLE prospects ADD COLUMN next_followup_at TIMESTAMP;

-- Scraper-sourced enrichment data
ALTER TABLE prospects ADD COLUMN scraper_data JSON;
ALTER TABLE prospects ADD COLUMN enriched_at TIMESTAMP;
ALTER TABLE prospects ADD COLUMN priority_tier VARCHAR(20);
ALTER TABLE prospects ADD COLUMN company_size INTEGER;
ALTER TABLE prospects ADD COLUMN decision_maker_score FLOAT;

-- =============================================================================
-- 3. Sequences table - Configurable email sequences
-- =============================================================================

CREATE TABLE IF NOT EXISTS sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    steps JSON NOT NULL,  -- Array of SequenceStep objects
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Insert default sequences
INSERT INTO sequences (name, description, steps, is_default) VALUES
(
    'standard',
    'Standard 5-email sequence over 14 days',
    '[
        {"step_number": 1, "delay_days": 0, "delay_hours": 0, "message_type": "email_initial"},
        {"step_number": 2, "delay_days": 3, "delay_hours": 0, "message_type": "email_followup_1"},
        {"step_number": 3, "delay_days": 5, "delay_hours": 0, "message_type": "email_followup_2"},
        {"step_number": 4, "delay_days": 7, "delay_hours": 0, "message_type": "email_followup_3"},
        {"step_number": 5, "delay_days": 10, "delay_hours": 0, "message_type": "email_followup_4"}
    ]',
    TRUE
),
(
    'aggressive',
    'Aggressive 5-email sequence over 7 days for high-priority prospects',
    '[
        {"step_number": 1, "delay_days": 0, "delay_hours": 0, "message_type": "email_initial"},
        {"step_number": 2, "delay_days": 1, "delay_hours": 0, "message_type": "email_followup_1"},
        {"step_number": 3, "delay_days": 2, "delay_hours": 0, "message_type": "email_followup_2"},
        {"step_number": 4, "delay_days": 3, "delay_hours": 0, "message_type": "email_followup_3"},
        {"step_number": 5, "delay_days": 5, "delay_hours": 0, "message_type": "email_followup_4"}
    ]',
    FALSE
),
(
    'gentle',
    'Gentle 4-email sequence over 21 days for nurture',
    '[
        {"step_number": 1, "delay_days": 0, "delay_hours": 0, "message_type": "email_initial"},
        {"step_number": 2, "delay_days": 7, "delay_hours": 0, "message_type": "email_followup_1"},
        {"step_number": 3, "delay_days": 14, "delay_hours": 0, "message_type": "email_followup_2"},
        {"step_number": 4, "delay_days": 21, "delay_hours": 0, "message_type": "email_followup_3"}
    ]',
    FALSE
);

-- =============================================================================
-- 4. Link campaigns to sequences
-- =============================================================================

ALTER TABLE outreach_campaigns ADD COLUMN sequence_id INTEGER REFERENCES sequences(id);

-- =============================================================================
-- 5. Domain warmup tracking
-- =============================================================================

CREATE TABLE IF NOT EXISTS domain_warmup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain VARCHAR(255) UNIQUE NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_week INTEGER DEFAULT 1,
    total_sent INTEGER DEFAULT 0,
    daily_sent_today INTEGER DEFAULT 0,
    last_send_date DATE,
    bounce_rate FLOAT DEFAULT 0,
    spam_rate FLOAT DEFAULT 0,
    is_warmed BOOLEAN DEFAULT FALSE,
    warmup_completed_at TIMESTAMP,
    notes TEXT
);

-- =============================================================================
-- 6. Deliverability metrics (daily snapshots)
-- =============================================================================

CREATE TABLE IF NOT EXISTS deliverability_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain VARCHAR(255) NOT NULL,
    date DATE NOT NULL,

    -- Volume metrics
    sent INTEGER DEFAULT 0,
    delivered INTEGER DEFAULT 0,
    bounced INTEGER DEFAULT 0,
    soft_bounced INTEGER DEFAULT 0,
    hard_bounced INTEGER DEFAULT 0,

    -- Engagement metrics
    opens INTEGER DEFAULT 0,
    unique_opens INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    unique_clicks INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,

    -- Negative signals
    spam_reports INTEGER DEFAULT 0,
    unsubscribes INTEGER DEFAULT 0,

    -- Calculated rates (stored for quick access)
    delivery_rate FLOAT,
    open_rate FLOAT,
    click_rate FLOAT,
    reply_rate FLOAT,
    bounce_rate FLOAT,
    spam_rate FLOAT,

    -- Health score (0-100)
    health_score INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(domain, date)
);

CREATE INDEX IF NOT EXISTS ix_deliverability_domain_date ON deliverability_metrics(domain, date);

-- =============================================================================
-- 7. A/B Tests
-- =============================================================================

CREATE TABLE IF NOT EXISTS ab_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES outreach_campaigns(id),
    name VARCHAR(200) NOT NULL,
    test_type VARCHAR(50) NOT NULL,  -- subject_line, body, cta, send_time

    -- Variants stored as JSON array
    variants JSON NOT NULL,
    -- Example: [{"id": "A", "content": "Subject A", "sent": 0, "opened": 0, "clicked": 0, "replied": 0}]

    traffic_split JSON NOT NULL,  -- [0.5, 0.5] for 50/50

    -- Statistical settings
    min_sample_size INTEGER DEFAULT 100,
    confidence_level FLOAT DEFAULT 0.95,

    -- Status
    status VARCHAR(50) DEFAULT 'running',  -- draft, running, concluded, cancelled
    winner VARCHAR(10),  -- A, B, C, etc.

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    concluded_at TIMESTAMP,

    -- Results
    results JSON  -- Statistical analysis results
);

CREATE INDEX IF NOT EXISTS ix_ab_tests_campaign ON ab_tests(campaign_id);
CREATE INDEX IF NOT EXISTS ix_ab_tests_status ON ab_tests(status);

-- =============================================================================
-- 8. Email validation results cache
-- =============================================================================

CREATE TABLE IF NOT EXISTS email_validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,

    -- Validation results
    is_valid BOOLEAN,
    is_disposable BOOLEAN DEFAULT FALSE,
    is_role_based BOOLEAN DEFAULT FALSE,  -- info@, support@, etc.
    is_catch_all BOOLEAN,
    has_mx_record BOOLEAN,

    -- Risk assessment
    risk_score FLOAT,  -- 0-1, higher = riskier
    risk_reasons JSON,  -- ["disposable_domain", "no_mx_record", etc.]

    -- Provider info
    domain VARCHAR(255),
    provider VARCHAR(100),  -- gmail, outlook, custom, etc.

    -- Timestamps
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,  -- Revalidate after this

    -- Source
    validation_source VARCHAR(50)  -- local, sendgrid, zerobounce, etc.
);

CREATE INDEX IF NOT EXISTS ix_email_validations_domain ON email_validations(domain);
CREATE INDEX IF NOT EXISTS ix_email_validations_valid ON email_validations(is_valid);

-- =============================================================================
-- 9. Scraper imports tracking
-- =============================================================================

CREATE TABLE IF NOT EXISTS scraper_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64),  -- SHA256 to detect duplicates

    -- Import stats
    prospects_found INTEGER DEFAULT 0,
    prospects_imported INTEGER DEFAULT 0,
    prospects_skipped INTEGER DEFAULT 0,
    prospects_updated INTEGER DEFAULT 0,

    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Campaign assignment
    campaign_id INTEGER REFERENCES outreach_campaigns(id)
);

CREATE INDEX IF NOT EXISTS ix_scraper_imports_status ON scraper_imports(status);
CREATE INDEX IF NOT EXISTS ix_scraper_imports_hash ON scraper_imports(file_hash);

-- =============================================================================
-- 10. Inbound replies tracking (for reply detection)
-- =============================================================================

CREATE TABLE IF NOT EXISTS inbound_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Sender info
    from_email VARCHAR(255) NOT NULL,
    from_name VARCHAR(255),

    -- Message info
    subject VARCHAR(500),
    body_text TEXT,
    body_html TEXT,

    -- Threading
    in_reply_to VARCHAR(255),  -- Message-ID being replied to
    references TEXT,  -- Message-ID chain

    -- Matching
    prospect_id INTEGER REFERENCES prospects(id),
    original_message_id INTEGER REFERENCES outreach_messages(id),
    matched_by VARCHAR(50),  -- email, message_id, subject

    -- Status
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,

    -- Raw data
    raw_headers JSON,

    -- Timestamps
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_inbound_emails_from ON inbound_emails(from_email);
CREATE INDEX IF NOT EXISTS ix_inbound_emails_prospect ON inbound_emails(prospect_id);
CREATE INDEX IF NOT EXISTS ix_inbound_emails_processed ON inbound_emails(processed);

-- =============================================================================
-- 11. Additional indexes for performance
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_prospects_email_status ON prospects(email_status);
CREATE INDEX IF NOT EXISTS ix_prospects_sequence_step ON prospects(campaign_id, current_sequence_step);
CREATE INDEX IF NOT EXISTS ix_prospects_next_followup ON prospects(next_followup_at);
CREATE INDEX IF NOT EXISTS ix_prospects_priority ON prospects(priority_tier);

CREATE INDEX IF NOT EXISTS ix_messages_delivered ON outreach_messages(delivered_at);
CREATE INDEX IF NOT EXISTS ix_messages_opened ON outreach_messages(opened_at);

-- =============================================================================
-- Done
-- =============================================================================
