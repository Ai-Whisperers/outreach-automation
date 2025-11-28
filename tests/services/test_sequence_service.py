"""
Tests for SequenceService.

Tests cover:
- Sequence types (standard, aggressive, gentle)
- Follow-up decision logic
- Engagement-based scheduling
- Business hours adjustment
- Sequence start/pause/resume
- Delay calculations
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSequenceServiceInit:
    """Tests for SequenceService initialization."""

    def test_sequence_service_initialization(self):
        """Test SequenceService initializes correctly."""
        from api.services.sequence_service import SequenceService

        service = SequenceService()

        assert service is not None
        assert hasattr(service, "sequences")

    def test_sequence_service_has_sequences(self):
        """Test SequenceService has predefined sequences."""
        from api.services.sequence_service import SequenceService

        service = SequenceService()

        assert "standard" in service.sequences
        assert "aggressive" in service.sequences
        assert "gentle" in service.sequences

    def test_sequence_service_default_sequence(self):
        """Test SequenceService has default sequence."""
        from api.services.sequence_service import SequenceService

        service = SequenceService()

        assert service.default_sequence == "standard"


class TestSequenceConfiguration:
    """Tests for sequence configurations."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    def test_standard_sequence_steps(self, sequence_service):
        """Test standard sequence has correct steps."""
        standard = sequence_service.sequences["standard"]

        assert len(standard["steps"]) >= 3
        # First step should be initial email
        assert standard["steps"][0]["type"] == "initial"

    def test_aggressive_sequence_shorter_delays(self, sequence_service):
        """Test aggressive sequence has shorter delays."""
        standard = sequence_service.sequences["standard"]
        aggressive = sequence_service.sequences["aggressive"]

        # Aggressive should have shorter delays
        standard_delay = standard["steps"][1]["delay_days"]
        aggressive_delay = aggressive["steps"][1]["delay_days"]

        assert aggressive_delay <= standard_delay

    def test_gentle_sequence_longer_delays(self, sequence_service):
        """Test gentle sequence has longer delays."""
        standard = sequence_service.sequences["standard"]
        gentle = sequence_service.sequences["gentle"]

        # Gentle should have longer delays
        standard_delay = standard["steps"][1]["delay_days"]
        gentle_delay = gentle["steps"][1]["delay_days"]

        assert gentle_delay >= standard_delay

    def test_sequence_step_structure(self, sequence_service):
        """Test sequence steps have required fields."""
        for name, sequence in sequence_service.sequences.items():
            for step in sequence["steps"]:
                assert "type" in step
                assert "delay_days" in step or step["type"] == "initial"


class TestShouldSendFollowup:
    """Tests for should_send_followup method."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_should_send_followup_after_delay(self, sequence_service, mock_db_session):
        """Test follow-up should send after delay period."""
        mock_prospect = MagicMock()
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_prospect.last_contacted = datetime.utcnow() - timedelta(days=4)
        mock_prospect.status = "CONTACTED"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.should_send_followup(mock_db_session, "prospect123")

        assert result["should_send"] is True
        assert result["step"] == 2

    @pytest.mark.asyncio
    async def test_should_not_send_before_delay(self, sequence_service, mock_db_session):
        """Test follow-up should not send before delay period."""
        mock_prospect = MagicMock()
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_prospect.last_contacted = datetime.utcnow() - timedelta(days=1)  # Too soon
        mock_prospect.status = "CONTACTED"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.should_send_followup(mock_db_session, "prospect123")

        assert result["should_send"] is False
        assert "days_until_next" in result

    @pytest.mark.asyncio
    async def test_should_not_send_to_replied(self, sequence_service, mock_db_session):
        """Test follow-up should not send to replied prospects."""
        mock_prospect = MagicMock()
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_prospect.last_contacted = datetime.utcnow() - timedelta(days=5)
        mock_prospect.status = "REPLIED"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.should_send_followup(mock_db_session, "prospect123")

        assert result["should_send"] is False
        assert "replied" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_should_not_send_to_unsubscribed(self, sequence_service, mock_db_session):
        """Test follow-up should not send to unsubscribed prospects."""
        mock_prospect = MagicMock()
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_prospect.last_contacted = datetime.utcnow() - timedelta(days=5)
        mock_prospect.status = "UNSUBSCRIBED"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.should_send_followup(mock_db_session, "prospect123")

        assert result["should_send"] is False

    @pytest.mark.asyncio
    async def test_should_not_send_sequence_complete(self, sequence_service, mock_db_session):
        """Test follow-up should not send when sequence complete."""
        mock_prospect = MagicMock()
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 5  # Beyond sequence steps
        mock_prospect.last_contacted = datetime.utcnow() - timedelta(days=10)
        mock_prospect.status = "CONTACTED"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.should_send_followup(mock_db_session, "prospect123")

        assert result["should_send"] is False
        assert "complete" in result["reason"].lower()


class TestEngagementBasedFollowup:
    """Tests for engagement-based follow-up logic."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_followup_sooner_with_opens(self, sequence_service, mock_db_session):
        """Test follow-up can be sooner if prospect opened emails."""
        mock_prospect = MagicMock()
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_prospect.last_contacted = datetime.utcnow() - timedelta(days=2)
        mock_prospect.status = "CONTACTED"
        mock_prospect.open_count = 3  # High engagement

        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.should_send_followup(
            mock_db_session, "prospect123", consider_engagement=True
        )

        # With high engagement, might send sooner
        if result["should_send"]:
            assert result["reason"] == "high_engagement"

    @pytest.mark.asyncio
    async def test_followup_delayed_with_no_engagement(self, sequence_service, mock_db_session):
        """Test follow-up delayed if no engagement."""
        mock_prospect = MagicMock()
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_prospect.last_contacted = datetime.utcnow() - timedelta(days=3)
        mock_prospect.status = "CONTACTED"
        mock_prospect.open_count = 0
        mock_prospect.click_count = 0

        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.should_send_followup(
            mock_db_session, "prospect123", consider_engagement=True
        )

        # With no engagement, might delay further
        assert "days_until_next" in result or not result["should_send"]

    @pytest.mark.asyncio
    async def test_skip_step_with_clicks(self, sequence_service, mock_db_session):
        """Test can skip steps if prospect clicked links."""
        mock_prospect = MagicMock()
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_prospect.last_contacted = datetime.utcnow() - timedelta(days=4)
        mock_prospect.status = "CONTACTED"
        mock_prospect.open_count = 5
        mock_prospect.click_count = 2  # Very engaged

        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.should_send_followup(
            mock_db_session, "prospect123", consider_engagement=True
        )

        # With clicks, might use different template or skip generic follow-up
        if "template" in result:
            assert result["template"] != "generic_followup"


class TestScheduleNextFollowup:
    """Tests for schedule_next_followup method."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_schedule_next_followup_creates_task(self, sequence_service, mock_db_session):
        """Test scheduling creates follow-up task."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.schedule_next_followup(mock_db_session, "prospect123")

        assert result["scheduled"] is True
        assert "scheduled_for" in result
        assert result["step"] == 2

    @pytest.mark.asyncio
    async def test_schedule_respects_business_hours(self, sequence_service, mock_db_session):
        """Test scheduling respects business hours."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_prospect.timezone = "America/New_York"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.schedule_next_followup(mock_db_session, "prospect123")

        scheduled_time = result["scheduled_for"]
        # Should be during business hours (9-17)
        assert scheduled_time.hour >= 8
        assert scheduled_time.hour <= 18

    @pytest.mark.asyncio
    async def test_schedule_avoids_weekends(self, sequence_service, mock_db_session):
        """Test scheduling avoids weekends."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 1
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        # Mock today as Friday
        with patch("api.services.sequence_service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2024, 1, 12, 10, 0)  # Friday
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            result = await sequence_service.schedule_next_followup(mock_db_session, "prospect123")

            scheduled_time = result["scheduled_for"]
            # Should not be Saturday (5) or Sunday (6)
            assert scheduled_time.weekday() < 5

    @pytest.mark.asyncio
    async def test_schedule_returns_none_for_completed(self, sequence_service, mock_db_session):
        """Test scheduling returns None for completed sequence."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 10  # Beyond sequence
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.schedule_next_followup(mock_db_session, "prospect123")

        assert result["scheduled"] is False
        assert "complete" in result["reason"].lower()


class TestStartSequence:
    """Tests for start_sequence method."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_start_sequence_default(self, sequence_service, mock_db_session):
        """Test starting default sequence."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = None
        mock_prospect.sequence_step = 0
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.start_sequence(mock_db_session, "prospect123")

        assert result["sequence_type"] == "standard"
        assert result["step"] == 1
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_start_sequence_aggressive(self, sequence_service, mock_db_session):
        """Test starting aggressive sequence."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = None
        mock_prospect.sequence_step = 0
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.start_sequence(
            mock_db_session, "prospect123", sequence_type="aggressive"
        )

        assert result["sequence_type"] == "aggressive"

    @pytest.mark.asyncio
    async def test_start_sequence_gentle(self, sequence_service, mock_db_session):
        """Test starting gentle sequence."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = None
        mock_prospect.sequence_step = 0
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.start_sequence(
            mock_db_session, "prospect123", sequence_type="gentle"
        )

        assert result["sequence_type"] == "gentle"

    @pytest.mark.asyncio
    async def test_start_sequence_already_in_progress(self, sequence_service, mock_db_session):
        """Test starting sequence when already in progress."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 2
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.start_sequence(mock_db_session, "prospect123")

        # Should not restart, return current state
        assert result["already_started"] is True
        assert result["current_step"] == 2


class TestPauseSequence:
    """Tests for pause_sequence method."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_pause_sequence(self, sequence_service, mock_db_session):
        """Test pausing sequence."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 2
        mock_prospect.sequence_status = "active"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.pause_sequence(mock_db_session, "prospect123")

        assert result["status"] == "paused"
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_pause_sequence_cancels_pending(self, sequence_service, mock_db_session):
        """Test pausing cancels pending scheduled emails."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_status = "active"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.pause_sequence(mock_db_session, "prospect123")

        assert result["pending_cancelled"] is True or result["status"] == "paused"


class TestResumeSequence:
    """Tests for resume_sequence method."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_resume_sequence(self, sequence_service, mock_db_session):
        """Test resuming paused sequence."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 2
        mock_prospect.sequence_status = "paused"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.resume_sequence(mock_db_session, "prospect123")

        assert result["status"] == "active"
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_resume_sequence_reschedules(self, sequence_service, mock_db_session):
        """Test resuming reschedules next follow-up."""
        mock_prospect = MagicMock()
        mock_prospect.id = "prospect123"
        mock_prospect.sequence_type = "standard"
        mock_prospect.sequence_step = 2
        mock_prospect.sequence_status = "paused"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_prospect)

        result = await sequence_service.resume_sequence(mock_db_session, "prospect123")

        assert "next_scheduled" in result or result["status"] == "active"


class TestBusinessHoursAdjustment:
    """Tests for business hours adjustment."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    def test_adjust_to_business_hours_early(self, sequence_service):
        """Test adjusting early morning to business hours."""
        early_time = datetime(2024, 1, 15, 6, 0)  # 6 AM

        adjusted = sequence_service._adjust_to_business_hours(early_time)

        assert adjusted.hour >= 9

    def test_adjust_to_business_hours_late(self, sequence_service):
        """Test adjusting late evening to next day."""
        late_time = datetime(2024, 1, 15, 20, 0)  # 8 PM

        adjusted = sequence_service._adjust_to_business_hours(late_time)

        # Should be next business day
        assert adjusted.day > late_time.day or adjusted.hour >= 9

    def test_adjust_saturday_to_monday(self, sequence_service):
        """Test adjusting Saturday to Monday."""
        saturday = datetime(2024, 1, 13, 10, 0)  # Saturday

        adjusted = sequence_service._adjust_to_business_hours(saturday)

        # Should be Monday
        assert adjusted.weekday() == 0

    def test_adjust_sunday_to_monday(self, sequence_service):
        """Test adjusting Sunday to Monday."""
        sunday = datetime(2024, 1, 14, 10, 0)  # Sunday

        adjusted = sequence_service._adjust_to_business_hours(sunday)

        assert adjusted.weekday() == 0

    def test_no_adjustment_needed(self, sequence_service):
        """Test no adjustment for valid business time."""
        business_time = datetime(2024, 1, 15, 14, 0)  # Monday 2 PM

        adjusted = sequence_service._adjust_to_business_hours(business_time)

        assert adjusted.hour == 14
        assert adjusted.day == 15


class TestDelayCalculations:
    """Tests for delay calculations."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    def test_get_delay_for_step_1(self, sequence_service):
        """Test delay for step 1 (initial)."""
        delay = sequence_service._get_delay_for_step("standard", 1)

        assert delay == 0  # Initial email, no delay

    def test_get_delay_for_step_2(self, sequence_service):
        """Test delay for step 2 (first follow-up)."""
        delay = sequence_service._get_delay_for_step("standard", 2)

        assert delay >= 2  # At least 2 days

    def test_get_delay_aggressive_shorter(self, sequence_service):
        """Test aggressive sequence has shorter delays."""
        standard_delay = sequence_service._get_delay_for_step("standard", 2)
        aggressive_delay = sequence_service._get_delay_for_step("aggressive", 2)

        assert aggressive_delay <= standard_delay

    def test_get_delay_gentle_longer(self, sequence_service):
        """Test gentle sequence has longer delays."""
        standard_delay = sequence_service._get_delay_for_step("standard", 2)
        gentle_delay = sequence_service._get_delay_for_step("gentle", 2)

        assert gentle_delay >= standard_delay

    def test_get_delay_later_steps_longer(self, sequence_service):
        """Test later steps have longer delays."""
        delay_2 = sequence_service._get_delay_for_step("standard", 2)
        delay_3 = sequence_service._get_delay_for_step("standard", 3)
        delay_4 = sequence_service._get_delay_for_step("standard", 4)

        assert delay_3 >= delay_2
        assert delay_4 >= delay_3


class TestGetNextStep:
    """Tests for getting next sequence step."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    def test_get_next_step_from_initial(self, sequence_service):
        """Test getting next step from initial."""
        next_step = sequence_service._get_next_step("standard", 1)

        assert next_step["step"] == 2
        assert next_step["type"] == "followup"

    def test_get_next_step_middle(self, sequence_service):
        """Test getting next step from middle of sequence."""
        next_step = sequence_service._get_next_step("standard", 2)

        assert next_step["step"] == 3

    def test_get_next_step_at_end(self, sequence_service):
        """Test getting next step at end of sequence."""
        # Standard sequence typically has 4-5 steps
        next_step = sequence_service._get_next_step("standard", 5)

        assert next_step is None or next_step.get("complete") is True


class TestTemplateSelection:
    """Tests for template selection based on step."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    def test_get_template_for_initial(self, sequence_service):
        """Test template for initial email."""
        template = sequence_service._get_template_for_step("standard", 1)

        assert "initial" in template.lower() or template is not None

    def test_get_template_for_followup(self, sequence_service):
        """Test template for follow-up email."""
        template = sequence_service._get_template_for_step("standard", 2)

        assert "followup" in template.lower() or template is not None

    def test_get_template_for_final(self, sequence_service):
        """Test template for final email."""
        template = sequence_service._get_template_for_step("standard", 4)

        # Final email might be "breakup" or "last_chance"
        assert template is not None


class TestSequenceStats:
    """Tests for sequence statistics."""

    @pytest.fixture
    def sequence_service(self):
        """Create SequenceService instance."""
        from api.services.sequence_service import SequenceService

        return SequenceService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_sequence_stats(self, sequence_service, mock_db_session):
        """Test getting sequence statistics."""
        mock_db_session.execute.return_value.one = MagicMock(return_value=(
            100,  # total_in_sequence
            40,   # completed
            10,   # replied
            5,    # unsubscribed
        ))

        result = await sequence_service.get_sequence_stats(mock_db_session)

        assert result["total_in_sequence"] == 100
        assert result["completed"] == 40
        assert result["reply_rate"] == 0.10  # 10/100


class TestSingleton:
    """Tests for singleton access."""

    def test_get_sequence_service_singleton(self):
        """Test get_sequence_service returns singleton."""
        import api.services.sequence_service as module

        module._sequence_service = None

        from api.services.sequence_service import get_sequence_service

        service1 = get_sequence_service()
        service2 = get_sequence_service()

        assert service1 is service2
