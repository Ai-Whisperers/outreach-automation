"""
Tests for WarmupService.

Tests cover:
- Domain warmup status
- 8-week warmup schedule
- Daily limit calculations
- Health status monitoring
- Bounce and spam rate thresholds
- Send permission checks
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWarmupServiceInit:
    """Tests for WarmupService initialization."""

    def test_warmup_service_initialization(self):
        """Test WarmupService initializes correctly."""
        from api.services.warmup_service import WarmupService

        service = WarmupService()

        assert service is not None
        assert hasattr(service, "warmup_schedule")

    def test_warmup_service_has_schedule(self):
        """Test WarmupService has 8-week schedule."""
        from api.services.warmup_service import WarmupService

        service = WarmupService()

        assert len(service.warmup_schedule) == 8
        # Week 1 should have lowest limits
        assert service.warmup_schedule[1] < service.warmup_schedule[8]

    def test_warmup_service_threshold_defaults(self):
        """Test WarmupService has threshold defaults."""
        from api.services.warmup_service import WarmupService

        service = WarmupService()

        assert hasattr(service, "bounce_threshold")
        assert hasattr(service, "spam_threshold")
        assert service.bounce_threshold <= 0.05  # 5% max
        assert service.spam_threshold <= 0.01  # 1% max


class TestGetWarmupStatus:
    """Tests for get_warmup_status method."""

    @pytest.fixture
    def warmup_service(self):
        """Create WarmupService instance."""
        from api.services.warmup_service import WarmupService

        return WarmupService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_warmup_status_new_domain(self, warmup_service, mock_db_session):
        """Test warmup status for new domain."""
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        result = await warmup_service.get_warmup_status(mock_db_session, "newdomain.com")

        assert result["week"] == 1
        assert result["status"] == "warmup"

    @pytest.mark.asyncio
    async def test_get_warmup_status_week_4(self, warmup_service, mock_db_session):
        """Test warmup status in week 4."""
        mock_domain = MagicMock()
        mock_domain.created_at = datetime.utcnow() - timedelta(weeks=4)
        mock_domain.total_sent = 500
        mock_domain.bounce_count = 5
        mock_domain.spam_count = 2
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        result = await warmup_service.get_warmup_status(mock_db_session, "domain.com")

        assert result["week"] == 4
        assert result["status"] == "warmup"

    @pytest.mark.asyncio
    async def test_get_warmup_status_fully_warmed(self, warmup_service, mock_db_session):
        """Test warmup status for fully warmed domain."""
        mock_domain = MagicMock()
        mock_domain.created_at = datetime.utcnow() - timedelta(weeks=10)
        mock_domain.total_sent = 5000
        mock_domain.bounce_count = 10
        mock_domain.spam_count = 5
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        result = await warmup_service.get_warmup_status(mock_db_session, "domain.com")

        assert result["week"] >= 8
        assert result["status"] == "warmed"

    @pytest.mark.asyncio
    async def test_get_warmup_status_includes_metrics(self, warmup_service, mock_db_session):
        """Test warmup status includes health metrics."""
        mock_domain = MagicMock()
        mock_domain.created_at = datetime.utcnow() - timedelta(weeks=3)
        mock_domain.total_sent = 300
        mock_domain.bounce_count = 6
        mock_domain.spam_count = 1
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        result = await warmup_service.get_warmup_status(mock_db_session, "domain.com")

        assert "bounce_rate" in result
        assert "spam_rate" in result
        assert "health_status" in result


class TestCanSend:
    """Tests for can_send method."""

    @pytest.fixture
    def warmup_service(self):
        """Create WarmupService instance."""
        from api.services.warmup_service import WarmupService

        return WarmupService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_can_send_healthy_domain(self, warmup_service, mock_db_session):
        """Test can_send returns True for healthy domain."""
        warmup_service.get_warmup_status = AsyncMock(return_value={
            "week": 4,
            "status": "warmup",
            "health_status": "healthy",
            "bounce_rate": 0.01,
            "spam_rate": 0.001,
            "daily_sent": 20,
            "daily_limit": 30,
        })

        result = await warmup_service.can_send(mock_db_session, "domain.com")

        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_can_send_at_daily_limit(self, warmup_service, mock_db_session):
        """Test can_send returns False at daily limit."""
        warmup_service.get_warmup_status = AsyncMock(return_value={
            "week": 4,
            "status": "warmup",
            "health_status": "healthy",
            "bounce_rate": 0.01,
            "spam_rate": 0.001,
            "daily_sent": 30,
            "daily_limit": 30,
        })

        result = await warmup_service.can_send(mock_db_session, "domain.com")

        assert result["allowed"] is False
        assert "limit" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_can_send_high_bounce_rate(self, warmup_service, mock_db_session):
        """Test can_send returns False for high bounce rate."""
        warmup_service.get_warmup_status = AsyncMock(return_value={
            "week": 4,
            "status": "warmup",
            "health_status": "critical",
            "bounce_rate": 0.08,  # 8% > 5% threshold
            "spam_rate": 0.001,
            "daily_sent": 10,
            "daily_limit": 30,
        })

        result = await warmup_service.can_send(mock_db_session, "domain.com")

        assert result["allowed"] is False
        assert "bounce" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_can_send_high_spam_rate(self, warmup_service, mock_db_session):
        """Test can_send returns False for high spam rate."""
        warmup_service.get_warmup_status = AsyncMock(return_value={
            "week": 4,
            "status": "warmup",
            "health_status": "critical",
            "bounce_rate": 0.01,
            "spam_rate": 0.02,  # 2% > 1% threshold
            "daily_sent": 10,
            "daily_limit": 30,
        })

        result = await warmup_service.can_send(mock_db_session, "domain.com")

        assert result["allowed"] is False
        assert "spam" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_can_send_paused_domain(self, warmup_service, mock_db_session):
        """Test can_send returns False for paused domain."""
        warmup_service.get_warmup_status = AsyncMock(return_value={
            "week": 4,
            "status": "paused",
            "health_status": "warning",
            "bounce_rate": 0.04,
            "spam_rate": 0.008,
            "daily_sent": 10,
            "daily_limit": 30,
        })

        result = await warmup_service.can_send(mock_db_session, "domain.com")

        assert result["allowed"] is False
        assert "paused" in result["reason"].lower()


class TestGetDailyLimit:
    """Tests for get_daily_limit method."""

    @pytest.fixture
    def warmup_service(self):
        """Create WarmupService instance."""
        from api.services.warmup_service import WarmupService

        return WarmupService()

    def test_get_daily_limit_week_1(self, warmup_service):
        """Test daily limit for week 1."""
        limit = warmup_service.get_daily_limit(week=1)

        # Week 1 should be conservative
        assert limit >= 5
        assert limit <= 20

    def test_get_daily_limit_week_2(self, warmup_service):
        """Test daily limit for week 2."""
        limit = warmup_service.get_daily_limit(week=2)

        assert limit > warmup_service.get_daily_limit(week=1)

    def test_get_daily_limit_week_4(self, warmup_service):
        """Test daily limit for week 4."""
        limit = warmup_service.get_daily_limit(week=4)

        # Week 4 should be moderate
        assert limit >= 20
        assert limit <= 50

    def test_get_daily_limit_week_8(self, warmup_service):
        """Test daily limit for week 8 (full capacity)."""
        limit = warmup_service.get_daily_limit(week=8)

        # Week 8 should be at or near full limit
        assert limit >= 40

    def test_get_daily_limit_progressive_increase(self, warmup_service):
        """Test daily limits increase progressively."""
        limits = [warmup_service.get_daily_limit(week=w) for w in range(1, 9)]

        # Each week should be >= previous week
        for i in range(1, len(limits)):
            assert limits[i] >= limits[i - 1]

    def test_get_daily_limit_beyond_week_8(self, warmup_service):
        """Test daily limit beyond week 8 uses full capacity."""
        week_8_limit = warmup_service.get_daily_limit(week=8)
        week_10_limit = warmup_service.get_daily_limit(week=10)

        assert week_10_limit >= week_8_limit


class TestHealthStatus:
    """Tests for health status monitoring."""

    @pytest.fixture
    def warmup_service(self):
        """Create WarmupService instance."""
        from api.services.warmup_service import WarmupService

        return WarmupService()

    def test_get_health_status_healthy(self, warmup_service):
        """Test healthy status for good metrics."""
        status = warmup_service._get_health_status(
            bounce_rate=0.01,  # 1%
            spam_rate=0.001,  # 0.1%
        )

        assert status == "healthy"

    def test_get_health_status_warning(self, warmup_service):
        """Test warning status for elevated metrics."""
        status = warmup_service._get_health_status(
            bounce_rate=0.03,  # 3% - approaching threshold
            spam_rate=0.005,  # 0.5%
        )

        assert status == "warning"

    def test_get_health_status_critical_bounce(self, warmup_service):
        """Test critical status for high bounce rate."""
        status = warmup_service._get_health_status(
            bounce_rate=0.06,  # 6% > 5% threshold
            spam_rate=0.001,
        )

        assert status == "critical"

    def test_get_health_status_critical_spam(self, warmup_service):
        """Test critical status for high spam rate."""
        status = warmup_service._get_health_status(
            bounce_rate=0.01,
            spam_rate=0.015,  # 1.5% > 1% threshold
        )

        assert status == "critical"

    def test_get_health_status_both_elevated(self, warmup_service):
        """Test status when both metrics elevated."""
        status = warmup_service._get_health_status(
            bounce_rate=0.04,  # 4%
            spam_rate=0.008,  # 0.8%
        )

        # Should be at least warning
        assert status in ["warning", "critical"]


class TestWarmupSchedule:
    """Tests for warmup schedule configuration."""

    @pytest.fixture
    def warmup_service(self):
        """Create WarmupService instance."""
        from api.services.warmup_service import WarmupService

        return WarmupService()

    def test_schedule_has_8_weeks(self, warmup_service):
        """Test schedule covers 8 weeks."""
        assert len(warmup_service.warmup_schedule) >= 8

    def test_schedule_week_1_conservative(self, warmup_service):
        """Test week 1 starts conservatively."""
        assert warmup_service.warmup_schedule[1] <= 20

    def test_schedule_week_8_full_capacity(self, warmup_service):
        """Test week 8 reaches full capacity."""
        assert warmup_service.warmup_schedule[8] >= 50

    def test_schedule_is_monotonic(self, warmup_service):
        """Test schedule increases monotonically."""
        for week in range(2, 9):
            assert warmup_service.warmup_schedule[week] >= warmup_service.warmup_schedule[week - 1]


class TestDomainRegistration:
    """Tests for domain registration in warmup."""

    @pytest.fixture
    def warmup_service(self):
        """Create WarmupService instance."""
        from api.services.warmup_service import WarmupService

        return WarmupService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.mark.asyncio
    async def test_register_domain(self, warmup_service, mock_db_session):
        """Test registering new domain for warmup."""
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        result = await warmup_service.register_domain(mock_db_session, "newdomain.com")

        assert result["domain"] == "newdomain.com"
        assert result["week"] == 1
        assert result["status"] == "warmup"
        mock_db_session.add.assert_called()
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_register_existing_domain(self, warmup_service, mock_db_session):
        """Test registering already existing domain."""
        mock_domain = MagicMock()
        mock_domain.domain = "existing.com"
        mock_domain.created_at = datetime.utcnow() - timedelta(weeks=3)
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        result = await warmup_service.register_domain(mock_db_session, "existing.com")

        # Should return existing domain info, not create new
        assert result["domain"] == "existing.com"
        assert result["week"] == 3


class TestPauseResume:
    """Tests for pause/resume warmup functionality."""

    @pytest.fixture
    def warmup_service(self):
        """Create WarmupService instance."""
        from api.services.warmup_service import WarmupService

        return WarmupService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_pause_warmup(self, warmup_service, mock_db_session):
        """Test pausing warmup for domain."""
        mock_domain = MagicMock()
        mock_domain.status = "warmup"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        result = await warmup_service.pause_warmup(mock_db_session, "domain.com")

        assert result["status"] == "paused"
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_resume_warmup(self, warmup_service, mock_db_session):
        """Test resuming warmup for domain."""
        mock_domain = MagicMock()
        mock_domain.status = "paused"
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        result = await warmup_service.resume_warmup(mock_db_session, "domain.com")

        assert result["status"] == "warmup"
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_auto_pause_on_critical(self, warmup_service, mock_db_session):
        """Test automatic pause when health becomes critical."""
        mock_domain = MagicMock()
        mock_domain.status = "warmup"
        mock_domain.bounce_rate = 0.08
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        await warmup_service.check_and_update_health(mock_db_session, "domain.com")

        # Should auto-pause on critical health
        assert mock_domain.status == "paused" or mock_db_session.commit.called


class TestMetricsTracking:
    """Tests for warmup metrics tracking."""

    @pytest.fixture
    def warmup_service(self):
        """Create WarmupService instance."""
        from api.services.warmup_service import WarmupService

        return WarmupService()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_record_send(self, warmup_service, mock_db_session):
        """Test recording a sent email."""
        mock_domain = MagicMock()
        mock_domain.total_sent = 100
        mock_domain.daily_sent = 10
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        await warmup_service.record_send(mock_db_session, "domain.com")

        assert mock_domain.total_sent == 101
        assert mock_domain.daily_sent == 11
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_record_bounce(self, warmup_service, mock_db_session):
        """Test recording a bounce."""
        mock_domain = MagicMock()
        mock_domain.bounce_count = 5
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        await warmup_service.record_bounce(mock_db_session, "domain.com")

        assert mock_domain.bounce_count == 6
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_record_spam_report(self, warmup_service, mock_db_session):
        """Test recording a spam report."""
        mock_domain = MagicMock()
        mock_domain.spam_count = 2
        mock_db_session.execute.return_value.scalar_one_or_none = MagicMock(return_value=mock_domain)

        await warmup_service.record_spam_report(mock_db_session, "domain.com")

        assert mock_domain.spam_count == 3
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_reset_daily_counters(self, warmup_service, mock_db_session):
        """Test resetting daily counters."""
        mock_domain = MagicMock()
        mock_domain.daily_sent = 50
        mock_db_session.execute.return_value.scalars.return_value.all = MagicMock(
            return_value=[mock_domain]
        )

        await warmup_service.reset_daily_counters(mock_db_session)

        assert mock_domain.daily_sent == 0
        mock_db_session.commit.assert_called()


class TestCalculateWeek:
    """Tests for warmup week calculation."""

    @pytest.fixture
    def warmup_service(self):
        """Create WarmupService instance."""
        from api.services.warmup_service import WarmupService

        return WarmupService()

    def test_calculate_week_day_1(self, warmup_service):
        """Test week calculation for day 1."""
        created_at = datetime.utcnow()
        week = warmup_service._calculate_week(created_at)

        assert week == 1

    def test_calculate_week_day_7(self, warmup_service):
        """Test week calculation for day 7."""
        created_at = datetime.utcnow() - timedelta(days=6)
        week = warmup_service._calculate_week(created_at)

        assert week == 1

    def test_calculate_week_day_8(self, warmup_service):
        """Test week calculation for day 8."""
        created_at = datetime.utcnow() - timedelta(days=7)
        week = warmup_service._calculate_week(created_at)

        assert week == 2

    def test_calculate_week_day_30(self, warmup_service):
        """Test week calculation for day 30."""
        created_at = datetime.utcnow() - timedelta(days=29)
        week = warmup_service._calculate_week(created_at)

        assert week == 5

    def test_calculate_week_day_60(self, warmup_service):
        """Test week calculation for day 60."""
        created_at = datetime.utcnow() - timedelta(days=59)
        week = warmup_service._calculate_week(created_at)

        assert week >= 8


class TestSingleton:
    """Tests for singleton access."""

    def test_get_warmup_service_singleton(self):
        """Test get_warmup_service returns singleton."""
        import api.services.warmup_service as module

        module._warmup_service = None

        from api.services.warmup_service import get_warmup_service

        service1 = get_warmup_service()
        service2 = get_warmup_service()

        assert service1 is service2
