"""
Unit tests for MessageValidator service.

Tests cover:
- Length validation for all message types
- Tone matching by ICP (solopreneur, sme, enterprise)
- Cultural fit validation for en/es/pt languages
- Personalization scoring
- CTA presence detection
- Subject line validation
- Message truncation
"""

import pytest

from api.services.message_validator import (
    CULTURAL_PATTERNS,
    CTA_PATTERNS,
    LENGTH_LIMITS,
    TONE_INDICATORS,
    MessageValidator,
    get_message_validator,
)


class TestMessageValidatorFactory:
    """Test factory function."""

    def test_get_message_validator(self):
        """Test factory returns MessageValidator instance."""
        validator = get_message_validator()
        assert isinstance(validator, MessageValidator)

    def test_factory_returns_new_instance(self):
        """Test factory creates new instances each time."""
        v1 = get_message_validator()
        v2 = get_message_validator()
        assert v1 is not v2


class TestLengthValidation:
    """Tests for validate_length method."""

    @pytest.fixture
    def validator(self):
        return MessageValidator()

    # LinkedIn Connection Request tests (50-200 chars)
    def test_connection_request_valid_length(self, validator):
        """Test valid connection request length."""
        message = "Hi John, noticed your work at Acme. Would love to connect and chat about AI. Worth a quick call?"
        result = validator.validate_length(message, "connection_request")

        assert result["is_valid"] is True
        assert result["unit"] == "chars"
        assert 50 <= result["count"] <= 200

    def test_connection_request_too_short(self, validator):
        """Test connection request below minimum."""
        message = "Hi, let's connect!"  # < 50 chars
        result = validator.validate_length(message, "connection_request")

        assert result["is_valid"] is False
        assert "Too short" in result.get("issue", "")

    def test_connection_request_too_long(self, validator):
        """Test connection request above maximum."""
        message = "Hi John, " + "x" * 200  # > 200 chars
        result = validator.validate_length(message, "connection_request")

        assert result["is_valid"] is False
        assert "Too long" in result.get("issue", "")

    def test_connection_request_exact_min(self, validator):
        """Test connection request at exact minimum."""
        message = "x" * 50
        result = validator.validate_length(message, "connection_request")
        assert result["is_valid"] is True

    def test_connection_request_exact_max(self, validator):
        """Test connection request at exact maximum."""
        message = "x" * 200
        result = validator.validate_length(message, "connection_request")
        assert result["is_valid"] is True

    # LinkedIn Message tests (100-500 chars)
    def test_linkedin_message_valid(self, validator):
        """Test valid LinkedIn DM length."""
        message = "Hi John, thanks for connecting! " + "x" * 150
        result = validator.validate_length(message, "linkedin_message")

        assert result["is_valid"] is True
        assert 100 <= result["count"] <= 500

    def test_linkedin_message_too_short(self, validator):
        """Test LinkedIn DM below minimum."""
        message = "Hi John, thanks!"
        result = validator.validate_length(message, "linkedin_message")
        assert result["is_valid"] is False

    # Email Initial tests (150-400 words)
    def test_email_initial_valid(self, validator):
        """Test valid initial email length."""
        words = ["word"] * 200
        message = " ".join(words)
        result = validator.validate_length(message, "email_initial")

        assert result["is_valid"] is True
        assert result["unit"] == "words"
        assert 150 <= result["count"] <= 400

    def test_email_initial_too_short(self, validator):
        """Test initial email below minimum words."""
        words = ["word"] * 50
        message = " ".join(words)
        result = validator.validate_length(message, "email_initial")

        assert result["is_valid"] is False
        assert "Too short" in result.get("issue", "")

    def test_email_initial_too_long(self, validator):
        """Test initial email above maximum words."""
        words = ["word"] * 500
        message = " ".join(words)
        result = validator.validate_length(message, "email_initial")

        assert result["is_valid"] is False
        assert "Too long" in result.get("issue", "")

    # Follow-up email tests
    @pytest.mark.parametrize("message_type,min_words,max_words", [
        ("email_followup_1", 80, 250),
        ("email_followup_2", 80, 250),
        ("email_followup_3", 50, 150),
        ("email_followup_4", 80, 200),
    ])
    def test_followup_emails_valid(self, validator, message_type, min_words, max_words):
        """Test valid follow-up email lengths."""
        words = ["word"] * ((min_words + max_words) // 2)
        message = " ".join(words)
        result = validator.validate_length(message, message_type)

        assert result["is_valid"] is True
        assert min_words <= result["count"] <= max_words

    def test_unknown_message_type(self, validator):
        """Test unknown message type returns valid."""
        result = validator.validate_length("Any message", "unknown_type")
        assert result["is_valid"] is True
        assert "No length limits defined" in result.get("message", "")


class TestToneValidation:
    """Tests for validate_tone method."""

    @pytest.fixture
    def validator(self):
        return MessageValidator()

    # Solopreneur tone tests
    def test_solopreneur_positive_tone(self, validator):
        """Test solopreneur-appropriate messaging."""
        message = "Quick and easy way to automate your content. Save time and scale yourself."
        result = validator.validate_tone(message, "solopreneur", "en")

        assert result["is_appropriate"] is True
        assert len(result["positive_matches"]) > 0
        assert "quick" in [m.lower() for m in result["positive_matches"]]

    def test_solopreneur_negative_tone(self, validator):
        """Test enterprise terms inappropriate for solopreneurs."""
        message = "Our enterprise solution requires a complex implementation project with governance."
        result = validator.validate_tone(message, "solopreneur", "en")

        assert result["is_appropriate"] is False
        assert len(result["negative_matches"]) > 0

    # SME tone tests
    def test_sme_positive_tone(self, validator):
        """Test SME-appropriate messaging."""
        message = "Improve your team productivity with measurable ROI and efficiency gains."
        result = validator.validate_tone(message, "sme", "en")

        assert result["is_appropriate"] is True
        assert any(m.lower() in ["roi", "productivity", "efficiency", "team"]
                  for m in result["positive_matches"])

    def test_sme_negative_tone(self, validator):
        """Test enterprise terms inappropriate for SMEs."""
        message = "This massive enterprise-wide transformation requires board approval."
        result = validator.validate_tone(message, "sme", "en")

        assert result["is_appropriate"] is False

    # Enterprise tone tests
    def test_enterprise_positive_tone(self, validator):
        """Test enterprise-appropriate messaging."""
        message = "Strategic partnership with comprehensive methodology for stakeholder alignment."
        result = validator.validate_tone(message, "enterprise", "en")

        assert result["is_appropriate"] is True

    def test_enterprise_negative_tone(self, validator):
        """Test casual terms inappropriate for enterprise."""
        message = "Here's a quick fix hack shortcut for cheap results."
        result = validator.validate_tone(message, "enterprise", "en")

        assert result["is_appropriate"] is False

    # Spanish language tests
    def test_spanish_solopreneur_tone(self, validator):
        """Test Spanish solopreneur messaging."""
        message = "Forma rápido y fácil de automatizar. Simple y efectivo."
        result = validator.validate_tone(message, "solopreneur", "es")

        assert result["is_appropriate"] is True
        assert any(m.lower() in ["rápido", "fácil", "simple", "automatizar"]
                  for m in result["positive_matches"])

    # Portuguese language tests
    def test_portuguese_sme_tone(self, validator):
        """Test Portuguese SME messaging."""
        message = "Aumente a produtividade da sua equipe com resultados e crescimento."
        result = validator.validate_tone(message, "sme", "pt")

        assert result["is_appropriate"] is True

    def test_unknown_icp_defaults_to_sme(self, validator):
        """Test unknown ICP defaults to SME indicators."""
        message = "Improve productivity and ROI for your team."
        result = validator.validate_tone(message, "unknown", "en")

        # Should use SME indicators as default
        assert "icp_type" in result


class TestCulturalFitValidation:
    """Tests for validate_cultural_fit method."""

    @pytest.fixture
    def validator(self):
        return MessageValidator()

    def test_english_no_restrictions(self, validator):
        """Test English has no cultural restrictions."""
        message = "Hey John, Cheers for connecting! Best regards."
        result = validator.validate_cultural_fit(message, "en")

        assert result["is_appropriate"] is True
        assert len(result["issues"]) == 0

    def test_spanish_avoid_english_terms(self, validator):
        """Test Spanish avoids anglicized terms."""
        message = "Hey Juan, Cheers por conectar! Best!"
        result = validator.validate_cultural_fit(message, "es")

        assert result["is_appropriate"] is False
        assert len(result["issues"]) > 0

    def test_spanish_appropriate_greeting(self, validator):
        """Test Spanish with appropriate greetings."""
        message = "Hola Juan, gracias por conectar. Saludos cordiales."
        result = validator.validate_cultural_fit(message, "es")

        assert result["is_appropriate"] is True

    def test_portuguese_avoid_english_terms(self, validator):
        """Test Portuguese avoids anglicized terms."""
        message = "Hey João, Cheers por conectar! Best!"
        result = validator.validate_cultural_fit(message, "pt")

        assert result["is_appropriate"] is False

    def test_portuguese_appropriate(self, validator):
        """Test Portuguese with appropriate greetings."""
        message = "Olá João, obrigado por conectar. Atenciosamente."
        result = validator.validate_cultural_fit(message, "pt")

        assert result["is_appropriate"] is True

    def test_short_message_no_greeting_check(self, validator):
        """Test short messages skip greeting check."""
        # Messages < 200 chars don't require native greeting
        message = "Gracias por conectar."
        result = validator.validate_cultural_fit(message, "es")

        assert result["is_appropriate"] is True


class TestPersonalizationScoring:
    """Tests for calculate_personalization_score method."""

    @pytest.fixture
    def validator(self):
        return MessageValidator()

    def test_full_personalization(self, validator):
        """Test message with all personalization elements."""
        message = (
            "Hi John, I noticed Acme Corp's impressive growth in the Technology sector. "
            "As VP of Marketing, you're likely facing challenges with manual content moderation. "
            "Companies in your position have seen 80% time savings with our solution."
        )
        context = {
            "first_name": "John",
            "company": "Acme Corp",
            "prospect_role": "VP of Marketing",
            "industry": "Technology",
            "pain_points": ["manual content moderation"],
            "key_metrics": ["80% time savings"],
        }

        result = validator.calculate_personalization_score(message, context)

        assert result["score"] >= 0.7
        assert "company_name" in result["elements_found"]
        assert "first_name" in result["elements_found"]

    def test_minimal_personalization(self, validator):
        """Test message with minimal personalization."""
        message = "Hi there, I wanted to reach out about our services."
        context = {
            "first_name": "John",
            "company": "Acme Corp",
        }

        result = validator.calculate_personalization_score(message, context)

        assert result["score"] < 0.4
        assert len(result["elements_found"]) == 0

    def test_company_name_personalization(self, validator):
        """Test company name adds 25% to score."""
        message = "I noticed Acme Corp's growth..."
        context = {"company": "Acme Corp"}

        result = validator.calculate_personalization_score(message, context)

        assert result["score"] >= 0.25
        assert "company_name" in result["elements_found"]

    def test_first_name_personalization(self, validator):
        """Test first name adds 15% to score."""
        message = "Hi John, wanted to connect..."
        context = {"first_name": "John"}

        result = validator.calculate_personalization_score(message, context)

        assert result["score"] >= 0.15
        assert "first_name" in result["elements_found"]

    def test_role_personalization(self, validator):
        """Test role reference adds 10% to score."""
        message = "As a Marketing leader, you likely..."
        context = {"role": "VP of Marketing"}

        result = validator.calculate_personalization_score(message, context)

        assert result["score"] >= 0.10
        assert "role" in result["elements_found"]

    def test_pain_point_personalization(self, validator):
        """Test pain point reference adds 20% to score."""
        message = "Many companies struggle with content moderation at scale."
        context = {"pain_points": ["content moderation challenges"]}

        result = validator.calculate_personalization_score(message, context)

        assert result["score"] >= 0.20
        assert "pain_point" in result["elements_found"]

    def test_metric_in_message(self, validator):
        """Test metric/number adds 10% to score."""
        message = "We've helped companies achieve 80% time savings and $50,000 cost reduction."
        context = {}

        result = validator.calculate_personalization_score(message, context)

        assert result["score"] >= 0.10
        assert "metric" in result["elements_found"]

    def test_missing_elements_tracked(self, validator):
        """Test missing elements are tracked."""
        message = "Generic message without personalization."
        context = {}

        result = validator.calculate_personalization_score(message, context)

        assert "elements_missing" in result
        assert "company_name" in result["elements_missing"]

    def test_score_capped_at_one(self, validator):
        """Test score never exceeds 1.0."""
        message = (
            "Hi John at Acme Corp in Technology industry. "
            "As VP Marketing facing content moderation issues. "
            "80% savings and $50K reduction with our 10+ solutions."
        )
        context = {
            "first_name": "John",
            "company": "Acme Corp",
            "role": "VP Marketing",
            "industry": "Technology",
            "pain_points": ["content moderation"],
            "key_metrics": ["80% savings"],
        }

        result = validator.calculate_personalization_score(message, context)

        assert result["score"] <= 1.0


class TestCTAValidation:
    """Tests for validate_cta method."""

    @pytest.fixture
    def validator(self):
        return MessageValidator()

    def test_question_cta(self, validator):
        """Test question mark as CTA."""
        message = "Would you be open to a quick chat?"
        result = validator.validate_cta(message, "en")

        assert result["has_cta"] is True

    def test_call_cta(self, validator):
        """Test call-related CTA."""
        message = "Let's schedule a quick call to discuss."
        result = validator.validate_cta(message, "en")

        assert result["has_cta"] is True
        assert any("call" in e or "schedule" in e for e in result["cta_elements"])

    def test_meeting_cta(self, validator):
        """Test meeting-related CTA."""
        message = "Worth booking a 15-minute meeting?"
        result = validator.validate_cta(message, "en")

        assert result["has_cta"] is True

    def test_no_cta(self, validator):
        """Test message without CTA."""
        message = "We provide great services for companies like yours."
        result = validator.validate_cta(message, "en")

        assert result["has_cta"] is False
        assert result["suggestion"] is not None

    def test_spanish_cta(self, validator):
        """Test Spanish CTAs."""
        message = "Te interesa agendar una reunión?"
        result = validator.validate_cta(message, "es")

        assert result["has_cta"] is True

    def test_portuguese_cta(self, validator):
        """Test Portuguese CTAs."""
        message = "Podemos agendar uma conversar?"
        result = validator.validate_cta(message, "pt")

        assert result["has_cta"] is True

    def test_multiple_ctas(self, validator):
        """Test message with multiple CTAs."""
        message = "Would you be interested in a call? Happy to schedule whenever works."
        result = validator.validate_cta(message, "en")

        assert result["has_cta"] is True
        assert len(result["cta_elements"]) >= 1


class TestSubjectValidation:
    """Tests for validate_subject method."""

    @pytest.fixture
    def validator(self):
        return MessageValidator()

    def test_valid_subject(self, validator):
        """Test valid subject line."""
        subject = "Quick question about Acme Corp"
        result = validator.validate_subject(subject, "en")

        assert result["is_valid"] is True
        assert 10 <= result["length"] <= 60

    def test_subject_too_long(self, validator):
        """Test subject over 60 characters."""
        subject = "This is a very long subject line that exceeds the recommended maximum length limit"
        result = validator.validate_subject(subject, "en")

        assert result["is_valid"] is False
        assert "too long" in result["issues"][0].lower()

    def test_subject_too_short(self, validator):
        """Test subject under 10 characters."""
        subject = "Hi there"
        result = validator.validate_subject(subject, "en")

        assert result["is_valid"] is False
        assert "too short" in result["issues"][0].lower()

    def test_spam_trigger_free(self, validator):
        """Test spam trigger word 'free'."""
        subject = "Free consultation for your team"
        result = validator.validate_subject(subject, "en")

        assert result["is_valid"] is False
        assert any("spam" in issue.lower() for issue in result["issues"])

    def test_spam_trigger_urgent(self, validator):
        """Test spam trigger word 'urgent'."""
        subject = "Urgent: Act now on this opportunity"
        result = validator.validate_subject(subject, "en")

        assert result["is_valid"] is False

    def test_spanish_spam_triggers(self, validator):
        """Test Spanish spam triggers."""
        subject = "Oferta gratis - urgente"
        result = validator.validate_subject(subject, "es")

        assert result["is_valid"] is False

    def test_portuguese_spam_triggers(self, validator):
        """Test Portuguese spam triggers."""
        subject = "Grátis - urgente agora"
        result = validator.validate_subject(subject, "pt")

        assert result["is_valid"] is False


class TestTruncateLinkedInConnection:
    """Tests for truncate_linkedin_connection method."""

    @pytest.fixture
    def validator(self):
        return MessageValidator()

    def test_no_truncation_needed(self, validator):
        """Test message under limit not truncated."""
        message = "Hi John, I'd love to connect!"
        result = validator.truncate_linkedin_connection(message)

        assert result == message

    def test_truncate_at_sentence(self, validator):
        """Test truncation at sentence boundary."""
        message = (
            "Hi John, I noticed your excellent work at Acme Corp. "
            "Your team has been doing amazing things with AI. "
            "I'd love to connect and share how we've helped similar companies. "
            "Would you be open to a chat sometime?"
        )
        result = validator.truncate_linkedin_connection(message)

        assert len(result) <= 200
        assert result.endswith(".") or result.endswith("...")

    def test_truncate_at_word_boundary(self, validator):
        """Test truncation at word boundary when no sentence end."""
        message = "Hi John, " + "word " * 50  # Long message without sentence end
        result = validator.truncate_linkedin_connection(message)

        assert len(result) <= 200
        assert result.endswith("...")
        assert not result.endswith(" ...")  # No trailing space

    def test_custom_max_length(self, validator):
        """Test custom max length."""
        message = "Hi John, this is a test message for truncation purposes."
        result = validator.truncate_linkedin_connection(message, max_chars=50)

        assert len(result) <= 50


class TestFullMessageValidation:
    """Tests for validate_message method (full validation)."""

    @pytest.fixture
    def validator(self):
        return MessageValidator()

    def test_valid_connection_request(self, validator, valid_connection_message, prospect_context):
        """Test fully valid connection request."""
        result = validator.validate_message(
            message=valid_connection_message,
            message_type="connection_request",
            icp_type="sme",
            language="en",
            prospect_context=prospect_context,
        )

        assert result["is_valid"] is True
        assert result["overall_score"] >= 0.6
        assert "length" in result
        assert "tone" in result
        assert "cta" in result

    def test_valid_email(self, validator, valid_email_message, prospect_context):
        """Test fully valid email."""
        result = validator.validate_message(
            message=valid_email_message,
            message_type="email_initial",
            icp_type="sme",
            language="en",
            prospect_context=prospect_context,
            subject="Quick question about Acme Corp",
        )

        assert result["is_valid"] is True
        assert "subject" in result

    def test_invalid_no_cta(self, validator, message_without_cta, prospect_context):
        """Test message without CTA fails."""
        result = validator.validate_message(
            message=message_without_cta,
            message_type="connection_request",
            icp_type="sme",
            language="en",
            prospect_context=prospect_context,
        )

        assert result["is_valid"] is False
        assert "Missing call-to-action" in result["issues"]

    def test_invalid_too_long(self, validator, invalid_long_connection_message):
        """Test message that's too long fails."""
        result = validator.validate_message(
            message=invalid_long_connection_message,
            message_type="connection_request",
            icp_type="sme",
            language="en",
        )

        assert result["is_valid"] is False
        assert any("long" in issue.lower() for issue in result["issues"])

    def test_low_personalization_suggestion(self, validator):
        """Test low personalization generates suggestion."""
        message = "Hi, I'd love to connect and chat about our services. Worth a call?"
        result = validator.validate_message(
            message=message,
            message_type="connection_request",
            icp_type="sme",
            language="en",
            prospect_context={"first_name": "John", "company": "Acme"},
        )

        assert any("personalization" in s.lower() for s in result["suggestions"])

    def test_overall_score_calculation(self, validator, prospect_context):
        """Test overall score is average of component scores."""
        message = (
            "Hi John at Acme Corp, noticed your work in Technology. "
            "Worth a quick call to discuss how we help companies like yours?"
        )
        result = validator.validate_message(
            message=message,
            message_type="connection_request",
            icp_type="sme",
            language="en",
            prospect_context=prospect_context,
        )

        assert 0 <= result["overall_score"] <= 1
        assert result["overall_score"] == pytest.approx(
            sum([
                1.0 if result["length"]["is_valid"] else 0.0,
                1.0 if result["tone"]["is_appropriate"] else 0.5,
                1.0 if result["cultural_fit"]["is_appropriate"] else 0.5,
                result["personalization"]["score"],
                1.0 if result["cta"]["has_cta"] else 0.0,
            ]) / 5,
            rel=0.01
        )

    def test_score_below_threshold_invalid(self, validator):
        """Test message with score below 0.6 is invalid."""
        # Short, no personalization, wrong tone
        message = "x" * 30  # Too short for connection request
        result = validator.validate_message(
            message=message,
            message_type="connection_request",
            icp_type="enterprise",
            language="en",
        )

        assert result["is_valid"] is False
        assert result["overall_score"] < 0.6
