"""
Unit tests for Pydantic models (request/response validation).

Tests cover:
- Campaign models validation
- Prospect models validation
- Message models validation
- Template models validation
- Outreach execution models
- Analytics models
- Field validators and constraints
"""

import pytest
from pydantic import ValidationError

from api.models.outreach_models import (
    ABTestResponse,
    ABTestResult,
    AnalyticsDashboard,
    CampaignCreate,
    CampaignListResponse,
    CampaignResponse,
    CampaignUpdate,
    DailyMetrics,
    EmailMessage,
    FollowUpSequence,
    FunnelStage,
    LinkedInConnectionMessage,
    LinkedInMessage,
    MessageApproveRequest,
    MessageApproveResponse,
    MessageBatchGenerateResponse,
    MessageEditRequest,
    MessageGenerateForProspectRequest,
    MessageGenerateRequest,
    MessageGenerateResponse,
    MessageListResponse,
    MessagePreviewRequest,
    MessageResponse,
    OutreachPauseRequest,
    OutreachStartRequest,
    OutreachStatusResponse,
    ProspectBulkImport,
    ProspectBulkImportResponse,
    ProspectCreate,
    ProspectCSVRow,
    ProspectListResponse,
    ProspectResponse,
    ProspectTimeline,
    ProspectTimelineResponse,
    ProspectUpdate,
    SendGridEvent,
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
    WebhookResponse,
)


class TestCampaignModels:
    """Tests for campaign request/response models."""

    def test_campaign_create_valid(self):
        """Test valid campaign creation."""
        campaign = CampaignCreate(
            name="Test Campaign",
            description="A test campaign",
            channels=["linkedin", "email"],
            daily_linkedin_limit=20,
            daily_email_limit=50,
        )

        assert campaign.name == "Test Campaign"
        assert campaign.channels == ["linkedin", "email"]

    def test_campaign_create_minimal(self):
        """Test campaign creation with minimal fields."""
        campaign = CampaignCreate(name="Minimal Campaign")

        assert campaign.name == "Minimal Campaign"
        assert campaign.channels == ["linkedin", "email"]  # Default
        assert campaign.daily_linkedin_limit == 20  # Default

    def test_campaign_create_empty_name_fails(self):
        """Test campaign creation with empty name fails."""
        with pytest.raises(ValidationError) as exc_info:
            CampaignCreate(name="")

        assert "min_length" in str(exc_info.value)

    def test_campaign_create_name_too_long(self):
        """Test campaign name max length."""
        with pytest.raises(ValidationError):
            CampaignCreate(name="x" * 201)

    def test_campaign_create_linkedin_limit_bounds(self):
        """Test LinkedIn limit constraints."""
        # Valid
        campaign = CampaignCreate(name="Test", daily_linkedin_limit=25)
        assert campaign.daily_linkedin_limit == 25

        # Too low
        with pytest.raises(ValidationError):
            CampaignCreate(name="Test", daily_linkedin_limit=0)

        # Too high
        with pytest.raises(ValidationError):
            CampaignCreate(name="Test", daily_linkedin_limit=26)

    def test_campaign_create_email_limit_bounds(self):
        """Test email limit constraints."""
        # Valid
        campaign = CampaignCreate(name="Test", daily_email_limit=200)
        assert campaign.daily_email_limit == 200

        # Too high
        with pytest.raises(ValidationError):
            CampaignCreate(name="Test", daily_email_limit=201)

    def test_campaign_update_partial(self):
        """Test partial campaign update."""
        update = CampaignUpdate(name="Updated Name")

        assert update.name == "Updated Name"
        assert update.description is None
        assert update.is_active is None

    def test_campaign_response(self):
        """Test campaign response model."""
        response = CampaignResponse(
            id=1,
            name="Test Campaign",
            description="Description",
            channels=["linkedin"],
            daily_linkedin_limit=20,
            daily_email_limit=50,
            is_active=True,
            prospect_count=10,
            message_count=25,
            created_at="2024-01-01T00:00:00",
        )

        assert response.id == 1
        assert response.prospect_count == 10

    def test_campaign_list_response(self):
        """Test campaign list response."""
        campaigns = [
            CampaignResponse(
                id=1,
                name="Campaign 1",
                description=None,
                channels=["email"],
                daily_linkedin_limit=20,
                daily_email_limit=50,
                is_active=True,
                created_at="2024-01-01T00:00:00",
            )
        ]
        response = CampaignListResponse(campaigns=campaigns, total=1)

        assert len(response.campaigns) == 1
        assert response.total == 1


class TestProspectModels:
    """Tests for prospect request/response models."""

    def test_prospect_create_valid(self):
        """Test valid prospect creation."""
        prospect = ProspectCreate(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            linkedin_url="https://linkedin.com/in/johndoe",
            company="Acme Corp",
            title="VP Marketing",
        )

        assert prospect.first_name == "John"
        assert prospect.email == "john@example.com"

    def test_prospect_create_minimal(self):
        """Test prospect creation with minimal fields."""
        prospect = ProspectCreate(
            first_name="John",
            last_name="Doe",
        )

        assert prospect.email is None
        assert prospect.linkedin_url is None

    def test_prospect_create_invalid_email(self):
        """Test prospect creation with invalid email."""
        with pytest.raises(ValidationError):
            ProspectCreate(
                first_name="John",
                last_name="Doe",
                email="not-an-email",
            )

    def test_prospect_create_invalid_linkedin_url(self):
        """Test prospect creation with invalid LinkedIn URL."""
        with pytest.raises(ValidationError) as exc_info:
            ProspectCreate(
                first_name="John",
                last_name="Doe",
                linkedin_url="https://twitter.com/johndoe",
            )

        assert "LinkedIn URL" in str(exc_info.value)

    def test_prospect_create_valid_linkedin_url(self):
        """Test prospect creation with valid LinkedIn URL."""
        prospect = ProspectCreate(
            first_name="John",
            last_name="Doe",
            linkedin_url="https://www.linkedin.com/in/johndoe",
        )

        assert "linkedin.com" in prospect.linkedin_url

    def test_prospect_csv_row(self):
        """Test CSV row model."""
        row = ProspectCSVRow(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            company="Acme",
            pain_points="Point 1, Point 2",  # Comma-separated
            metrics='{"revenue": "$5M"}',  # JSON string
        )

        assert row.first_name == "John"
        assert row.pain_points == "Point 1, Point 2"

    def test_prospect_bulk_import(self):
        """Test bulk import request model."""
        import_req = ProspectBulkImport(
            csv_content="first_name,last_name\nJohn,Doe",
            skip_duplicates=True,
            auto_link_brand_briefs=True,
        )

        assert import_req.skip_duplicates is True
        assert len(import_req.csv_content) > 10

    def test_prospect_bulk_import_csv_too_short(self):
        """Test bulk import with CSV too short."""
        with pytest.raises(ValidationError):
            ProspectBulkImport(csv_content="abc")

    def test_prospect_update_partial(self):
        """Test partial prospect update."""
        update = ProspectUpdate(
            first_name="Updated",
            status="researched",
        )

        assert update.first_name == "Updated"
        assert update.status == "researched"
        assert update.last_name is None

    def test_prospect_response(self):
        """Test prospect response model."""
        response = ProspectResponse(
            id=1,
            campaign_id=1,
            full_name="John Doe",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            linkedin_url="https://linkedin.com/in/johndoe",
            company="Acme",
            title="VP",
            industry="Tech",
            location="SF",
            status="new",
            engagement_score=0.5,
            personalization_score=0.8,
            message_count=2,
            last_contacted_at=None,
            created_at="2024-01-01T00:00:00",
        )

        assert response.full_name == "John Doe"
        assert response.engagement_score == 0.5

    def test_prospect_timeline(self):
        """Test prospect timeline model."""
        timeline = ProspectTimeline(
            timestamp="2024-01-01T00:00:00",
            event_type="message_sent",
            channel="email",
            details={"subject": "Hello"},
        )

        assert timeline.event_type == "message_sent"


class TestMessageModels:
    """Tests for message request/response models."""

    def test_message_generate_request_defaults(self):
        """Test message generate request defaults."""
        request = MessageGenerateRequest()

        assert request.message_types == ["connection_request", "email_initial"]
        assert request.language == "en"
        assert request.icp_override is None

    def test_message_generate_request_custom(self):
        """Test custom message generate request."""
        request = MessageGenerateRequest(
            message_types=["email_initial", "email_followup_1"],
            language="es",
            icp_override="enterprise",
            prospect_ids=[1, 2, 3],
        )

        assert request.language == "es"
        assert request.icp_override == "enterprise"
        assert len(request.prospect_ids) == 3

    def test_linkedin_connection_message(self):
        """Test LinkedIn connection message model."""
        msg = LinkedInConnectionMessage(
            message="Hi John, let's connect!",
            character_count=25,
            personalization_elements=["first_name"],
            validation_passed=True,
        )

        assert msg.validation_passed is True
        assert len(msg.message) <= 200

    def test_linkedin_connection_message_max_length(self):
        """Test LinkedIn connection message max length."""
        with pytest.raises(ValidationError):
            LinkedInConnectionMessage(
                message="x" * 201,
                character_count=201,
                personalization_elements=[],
                validation_passed=False,
            )

    def test_email_message(self):
        """Test email message model."""
        email = EmailMessage(
            subject="Quick question",
            body="Hi John, I noticed...",
            word_count=50,
            personalization_score=0.8,
            personalization_elements=["first_name", "company"],
        )

        assert email.subject == "Quick question"
        assert email.personalization_score == 0.8

    def test_email_message_subject_max_length(self):
        """Test email subject max length."""
        with pytest.raises(ValidationError):
            EmailMessage(
                subject="x" * 101,
                body="Body",
                word_count=1,
                personalization_score=0.5,
                personalization_elements=[],
            )

    def test_followup_sequence(self):
        """Test follow-up email sequence model."""
        email = EmailMessage(
            subject="Follow up",
            body="Just checking in...",
            word_count=20,
            personalization_score=0.6,
            personalization_elements=[],
        )

        sequence = FollowUpSequence(
            follow_up_1=email,
            follow_up_2=email,
            follow_up_3=email,
            follow_up_4=email,
        )

        assert sequence.follow_up_1.subject == "Follow up"

    def test_message_generate_response(self):
        """Test message generate response model."""
        response = MessageGenerateResponse(
            prospect_id=1,
            prospect_name="John Doe",
            company="Acme",
            icp_type="sme",
            language="en",
            linkedin_connection=None,
            cold_email=None,
            messages_created=0,
            generation_time_ms=150,
        )

        assert response.prospect_id == 1
        assert response.generation_time_ms == 150

    def test_message_edit_request(self):
        """Test message edit request."""
        edit = MessageEditRequest(
            subject="New Subject",
            content="New content here",
        )

        assert edit.subject == "New Subject"

    def test_message_approve_request(self):
        """Test message approve request."""
        approve = MessageApproveRequest(message_ids=[1, 2, 3])

        assert len(approve.message_ids) == 3


class TestTemplateModels:
    """Tests for template request/response models."""

    def test_template_create_valid(self):
        """Test valid template creation."""
        template = TemplateCreate(
            name="Cold Email Template A",
            channel="email",
            message_type="email_initial",
            language="en",
            subject_template="Hi {{first_name}}",
            content_template="Hello {{first_name}} at {{company}}...",
            variant="A",
        )

        assert template.name == "Cold Email Template A"
        assert template.channel == "email"
        assert template.variant == "A"

    def test_template_create_content_min_length(self):
        """Test template content minimum length."""
        with pytest.raises(ValidationError):
            TemplateCreate(
                name="Test",
                channel="email",
                message_type="email_initial",
                content_template="short",  # < 10 chars
            )

    def test_template_update_partial(self):
        """Test partial template update."""
        update = TemplateUpdate(
            name="Updated Name",
            is_active=False,
        )

        assert update.name == "Updated Name"
        assert update.is_active is False
        assert update.content_template is None


class TestOutreachModels:
    """Tests for outreach execution models."""

    def test_outreach_start_request_defaults(self):
        """Test outreach start request defaults."""
        request = OutreachStartRequest()

        assert request.channels is None
        assert request.prospect_ids is None

    def test_outreach_start_request_specific(self):
        """Test specific outreach start request."""
        request = OutreachStartRequest(
            channels=["email"],
            prospect_ids=[1, 2, 3],
        )

        assert request.channels == ["email"]
        assert len(request.prospect_ids) == 3

    def test_outreach_pause_request(self):
        """Test outreach pause request."""
        request = OutreachPauseRequest(cancel_scheduled=True)

        assert request.cancel_scheduled is True

    def test_outreach_status_response(self):
        """Test outreach status response."""
        status = OutreachStatusResponse(
            campaign_id=1,
            is_active=True,
            started_at="2024-01-01T00:00:00",
            paused_at=None,
            today_linkedin_sent=5,
            today_linkedin_remaining=15,
            today_email_sent=10,
            today_email_remaining=40,
            total_scheduled=50,
            total_sent=100,
        )

        assert status.is_active is True
        assert status.today_linkedin_remaining == 15


class TestAnalyticsModels:
    """Tests for analytics models."""

    def test_daily_metrics(self):
        """Test daily metrics model."""
        metrics = DailyMetrics(
            date="2024-01-15",
            linkedin_sent=10,
            email_sent=25,
            connections_accepted=3,
            emails_opened=15,
            emails_clicked=5,
            replies_received=2,
        )

        assert metrics.linkedin_sent == 10
        assert metrics.emails_opened == 15

    def test_funnel_stage(self):
        """Test funnel stage model."""
        stage = FunnelStage(
            stage="contacted",
            count=50,
            percentage=25.5,
        )

        assert stage.stage == "contacted"
        assert stage.percentage == 25.5

    def test_analytics_dashboard(self):
        """Test full analytics dashboard model."""
        dashboard = AnalyticsDashboard(
            campaign_id=1,
            period="30d",
            total_prospects=100,
            total_sent=50,
            linkedin_sent=20,
            email_sent=30,
            connections_accepted=10,
            connection_rate=0.5,
            emails_opened=20,
            open_rate=0.67,
            emails_clicked=8,
            click_rate=0.27,
            replies_received=5,
            reply_rate=0.10,
            prospects_by_status={"new": 50, "contacted": 30, "replied": 20},
            funnel=[
                FunnelStage(stage="new", count=100, percentage=100.0),
                FunnelStage(stage="contacted", count=50, percentage=50.0),
            ],
            daily_trends=[],
        )

        assert dashboard.total_prospects == 100
        assert dashboard.connection_rate == 0.5
        assert len(dashboard.funnel) == 2

    def test_ab_test_result(self):
        """Test A/B test result model."""
        result = ABTestResult(
            variant="A",
            sent_count=100,
            open_rate=0.45,
            click_rate=0.12,
            reply_rate=0.08,
            winner=True,
        )

        assert result.variant == "A"
        assert result.winner is True

    def test_ab_test_response(self):
        """Test A/B test response model."""
        response = ABTestResponse(
            message_type="email_initial",
            variants=[
                ABTestResult(
                    variant="A",
                    sent_count=100,
                    open_rate=0.45,
                    click_rate=0.12,
                    reply_rate=0.08,
                    winner=True,
                ),
                ABTestResult(
                    variant="B",
                    sent_count=100,
                    open_rate=0.40,
                    click_rate=0.10,
                    reply_rate=0.05,
                    winner=False,
                ),
            ],
            statistical_significance=0.95,
            recommendation="Use variant A - 20% higher reply rate",
        )

        assert len(response.variants) == 2
        assert response.statistical_significance == 0.95


class TestWebhookModels:
    """Tests for webhook models."""

    def test_sendgrid_event(self):
        """Test SendGrid webhook event model."""
        event = SendGridEvent(
            event="open",
            email="john@example.com",
            timestamp=1705000000,
            sg_message_id="abc123",
            useragent="Mozilla/5.0",
            ip="192.168.1.1",
        )

        assert event.event == "open"
        assert event.email == "john@example.com"

    def test_sendgrid_event_click(self):
        """Test SendGrid click event with URL."""
        event = SendGridEvent(
            event="click",
            email="john@example.com",
            url="https://example.com/link",
        )

        assert event.event == "click"
        assert event.url == "https://example.com/link"

    def test_webhook_response(self):
        """Test webhook response model."""
        response = WebhookResponse(
            status="ok",
            events_processed=5,
        )

        assert response.status == "ok"
        assert response.events_processed == 5


class TestLiteralTypes:
    """Tests for Literal type constraints."""

    def test_valid_channel_types(self):
        """Test valid channel types."""
        for channel in ["linkedin", "email"]:
            request = OutreachStartRequest(channels=[channel])
            assert channel in request.channels

    def test_invalid_channel_type(self):
        """Test invalid channel type."""
        with pytest.raises(ValidationError):
            OutreachStartRequest(channels=["twitter"])

    def test_valid_message_types(self):
        """Test valid message types."""
        valid_types = [
            "connection_request",
            "linkedin_message",
            "email_initial",
            "email_followup_1",
            "email_followup_2",
            "email_followup_3",
            "email_followup_4",
        ]
        request = MessageGenerateRequest(message_types=valid_types[:2])
        assert len(request.message_types) == 2

    def test_invalid_message_type(self):
        """Test invalid message type."""
        with pytest.raises(ValidationError):
            MessageGenerateRequest(message_types=["invalid_type"])

    def test_valid_icp_types(self):
        """Test valid ICP types."""
        for icp in ["solopreneur", "sme", "enterprise"]:
            request = MessageGenerateRequest(icp_override=icp)
            assert request.icp_override == icp

    def test_invalid_icp_type(self):
        """Test invalid ICP type."""
        with pytest.raises(ValidationError):
            MessageGenerateRequest(icp_override="invalid")

    def test_valid_language_types(self):
        """Test valid language types."""
        for lang in ["en", "es", "pt"]:
            request = MessageGenerateRequest(language=lang)
            assert request.language == lang

    def test_invalid_language_type(self):
        """Test invalid language type."""
        with pytest.raises(ValidationError):
            MessageGenerateRequest(language="fr")

    def test_valid_prospect_status_types(self):
        """Test valid prospect status types."""
        valid_statuses = [
            "new", "researched", "scheduled", "contacted",
            "connected", "engaged", "replied", "meeting_scheduled",
            "converted", "opted_out", "bounced",
        ]
        for status in valid_statuses:
            update = ProspectUpdate(status=status)
            assert update.status == status

    def test_invalid_prospect_status(self):
        """Test invalid prospect status."""
        with pytest.raises(ValidationError):
            ProspectUpdate(status="invalid_status")
