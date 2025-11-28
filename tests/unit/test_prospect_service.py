"""
Unit tests for ProspectService.

Tests cover:
- CRUD operations
- CSV import and parsing
- Deduplication logic
- Brand brief linking
- Prospect queries
- Email validation
"""

import pytest
import pytest_asyncio

from api.database.outreach_models import Prospect, ProspectStatus
from api.services.prospect_service import ProspectService, get_prospect_service


class TestProspectServiceFactory:
    """Test factory function."""

    @pytest.mark.asyncio
    async def test_get_prospect_service(self, db_session):
        """Test factory returns ProspectService instance."""
        service = get_prospect_service(db_session)
        assert isinstance(service, ProspectService)

    @pytest.mark.asyncio
    async def test_factory_with_custom_dir(self, db_session, tmp_path):
        """Test factory with custom brand briefs directory."""
        service = get_prospect_service(db_session, tmp_path)
        assert service.brand_briefs_dir == tmp_path


class TestCreateProspect:
    """Tests for create_prospect method."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    @pytest.mark.asyncio
    async def test_create_basic_prospect(self, service, sample_campaign):
        """Test creating a basic prospect."""
        prospect = await service.create_prospect(
            campaign_id=sample_campaign.id,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )

        assert prospect.id is not None
        assert prospect.first_name == "John"
        assert prospect.last_name == "Doe"
        assert prospect.email == "john@example.com"
        assert prospect.status == ProspectStatus.NEW

    @pytest.mark.asyncio
    async def test_create_prospect_with_all_fields(self, service, sample_campaign):
        """Test creating a prospect with all fields."""
        prospect = await service.create_prospect(
            campaign_id=sample_campaign.id,
            first_name="Jane",
            last_name="Smith",
            email="jane@techcorp.com",
            linkedin_url="https://linkedin.com/in/janesmith",
            company="TechCorp",
            title="CEO",
            industry="SaaS",
            location="New York",
            pain_points=["Manual moderation", "Scaling"],
            metrics={"revenue": "$5M"},
        )

        assert prospect.company == "TechCorp"
        assert prospect.title == "CEO"
        assert prospect.personalization_data["pain_points"] == ["Manual moderation", "Scaling"]
        assert prospect.personalization_data["metrics"]["revenue"] == "$5M"

    @pytest.mark.asyncio
    async def test_create_prospect_full_name(self, service, sample_campaign):
        """Test full_name property."""
        prospect = await service.create_prospect(
            campaign_id=sample_campaign.id,
            first_name="John",
            last_name="Doe",
        )

        assert prospect.full_name == "John Doe"

    @pytest.mark.asyncio
    async def test_create_prospect_auto_link_brand_brief(
        self, service, sample_campaign, temp_brand_briefs_dir
    ):
        """Test auto-linking to brand brief."""
        service.brand_briefs_dir = temp_brand_briefs_dir

        prospect = await service.create_prospect(
            campaign_id=sample_campaign.id,
            first_name="Jane",
            last_name="Smith",
            company="TechCorp",
            auto_link_brand_brief=True,
        )

        assert prospect.brand_brief_path is not None
        assert "techcorp" in prospect.brand_brief_path.lower()


class TestGetProspect:
    """Tests for get_prospect method."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    @pytest.mark.asyncio
    async def test_get_existing_prospect(self, service, sample_prospect):
        """Test getting an existing prospect."""
        result = await service.get_prospect(sample_prospect.id)

        assert result is not None
        assert result.id == sample_prospect.id
        assert result.first_name == sample_prospect.first_name

    @pytest.mark.asyncio
    async def test_get_nonexistent_prospect(self, service):
        """Test getting a non-existent prospect."""
        result = await service.get_prospect(99999)

        assert result is None


class TestGetProspects:
    """Tests for get_prospects method."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    @pytest.mark.asyncio
    async def test_get_prospects_basic(self, service, sample_campaign, sample_prospect):
        """Test getting prospects for a campaign."""
        prospects, total = await service.get_prospects(sample_campaign.id)

        assert len(prospects) >= 1
        assert total >= 1

    @pytest.mark.asyncio
    async def test_get_prospects_with_status_filter(
        self, service, sample_campaign, sample_prospect
    ):
        """Test filtering prospects by status."""
        prospects, total = await service.get_prospects(
            sample_campaign.id,
            status=ProspectStatus.NEW,
        )

        assert all(p.status == ProspectStatus.NEW for p in prospects)

    @pytest.mark.asyncio
    async def test_get_prospects_pagination(self, service, sample_campaign):
        """Test prospect pagination."""
        # Create multiple prospects
        for i in range(5):
            await service.create_prospect(
                campaign_id=sample_campaign.id,
                first_name=f"User{i}",
                last_name="Test",
            )

        prospects, total = await service.get_prospects(
            sample_campaign.id,
            limit=2,
            offset=0,
        )

        assert len(prospects) == 2
        assert total >= 5


class TestUpdateProspect:
    """Tests for update_prospect method."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    @pytest.mark.asyncio
    async def test_update_prospect_fields(self, service, sample_prospect):
        """Test updating prospect fields."""
        result = await service.update_prospect(
            sample_prospect.id,
            first_name="Updated",
            company="New Company",
        )

        assert result.first_name == "Updated"
        assert result.company == "New Company"
        assert result.updated_at is not None

    @pytest.mark.asyncio
    async def test_update_nonexistent_prospect(self, service):
        """Test updating non-existent prospect."""
        result = await service.update_prospect(99999, first_name="Test")

        assert result is None


class TestDeleteProspect:
    """Tests for delete_prospect method."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    @pytest.mark.asyncio
    async def test_delete_prospect(self, service, sample_prospect):
        """Test deleting a prospect."""
        result = await service.delete_prospect(sample_prospect.id)

        assert result is True

        # Verify deleted
        deleted = await service.get_prospect(sample_prospect.id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_prospect(self, service):
        """Test deleting non-existent prospect."""
        result = await service.delete_prospect(99999)

        assert result is False


class TestUpdateStatus:
    """Tests for update_status method."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    @pytest.mark.asyncio
    async def test_update_status(self, service, sample_prospect):
        """Test updating prospect status."""
        result = await service.update_status(
            sample_prospect.id,
            ProspectStatus.RESEARCHED,
        )

        assert result.status == ProspectStatus.RESEARCHED

    @pytest.mark.asyncio
    async def test_update_to_contacted_sets_timestamp(self, service, sample_prospect):
        """Test setting CONTACTED status updates last_contacted_at."""
        result = await service.update_status(
            sample_prospect.id,
            ProspectStatus.CONTACTED,
        )

        assert result.status == ProspectStatus.CONTACTED
        assert result.last_contacted_at is not None


class TestCSVImport:
    """Tests for import_from_csv method."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    @pytest.mark.asyncio
    async def test_import_valid_csv(self, service, sample_campaign, sample_csv_content):
        """Test importing valid CSV."""
        result = await service.import_from_csv(
            campaign_id=sample_campaign.id,
            csv_content=sample_csv_content,
        )

        assert result["added_count"] == 3
        assert result["duplicates_skipped"] == 0
        assert result["invalid_skipped"] == 0
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_import_csv_with_errors(self, service, sample_campaign, sample_csv_with_errors):
        """Test importing CSV with validation errors."""
        result = await service.import_from_csv(
            campaign_id=sample_campaign.id,
            csv_content=sample_csv_with_errors,
        )

        assert result["invalid_skipped"] >= 2
        assert result["added_count"] >= 1
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_import_csv_skip_duplicates(self, service, sample_campaign):
        """Test duplicate skipping during import."""
        csv_content = """first_name,last_name,email,linkedin_url,company
John,Doe,john@example.com,https://linkedin.com/in/johndoe,Acme
Jane,Smith,jane@example.com,https://linkedin.com/in/janesmith,Tech
"""
        # First import
        await service.import_from_csv(
            campaign_id=sample_campaign.id,
            csv_content=csv_content,
            skip_duplicates=True,
        )

        # Second import with same data
        result = await service.import_from_csv(
            campaign_id=sample_campaign.id,
            csv_content=csv_content,
            skip_duplicates=True,
        )

        assert result["duplicates_skipped"] == 2
        assert result["added_count"] == 0

    @pytest.mark.asyncio
    async def test_import_csv_missing_required_columns(self, service, sample_campaign):
        """Test import fails with missing required columns."""
        csv_content = """email,company
john@example.com,Acme
"""
        result = await service.import_from_csv(
            campaign_id=sample_campaign.id,
            csv_content=csv_content,
        )

        assert len(result["errors"]) > 0
        assert "Missing required columns" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_import_empty_csv(self, service, sample_campaign):
        """Test import of empty CSV."""
        csv_content = "first_name,last_name,email\n"
        result = await service.import_from_csv(
            campaign_id=sample_campaign.id,
            csv_content=csv_content,
        )

        assert result["added_count"] == 0

    @pytest.mark.asyncio
    async def test_import_csv_with_pain_points(self, service, sample_campaign):
        """Test importing CSV with pain points."""
        csv_content = """first_name,last_name,email,company,pain_points
John,Doe,john@example.com,Acme,"Manual moderation, Scaling issues, Cost concerns"
"""
        result = await service.import_from_csv(
            campaign_id=sample_campaign.id,
            csv_content=csv_content,
        )

        assert result["added_count"] == 1

        # Verify pain points were parsed
        prospects, _ = await service.get_prospects(sample_campaign.id)
        prospect = next(p for p in prospects if p.email == "john@example.com")
        assert len(prospect.personalization_data["pain_points"]) == 3

    @pytest.mark.asyncio
    async def test_import_csv_with_metrics_json(self, service, sample_campaign):
        """Test importing CSV with JSON metrics."""
        csv_content = '''first_name,last_name,email,company,metrics
John,Doe,john@example.com,Acme,"{""revenue"": ""$5M"", ""employees"": ""50""}"
'''
        result = await service.import_from_csv(
            campaign_id=sample_campaign.id,
            csv_content=csv_content,
        )

        assert result["added_count"] == 1

        prospects, _ = await service.get_prospects(sample_campaign.id)
        prospect = next(p for p in prospects if p.email == "john@example.com")
        assert prospect.personalization_data["metrics"]["revenue"] == "$5M"


class TestBrandBriefLinking:
    """Tests for brand brief linking methods."""

    @pytest_asyncio.fixture
    async def service(self, db_session, temp_brand_briefs_dir):
        svc = ProspectService(db_session)
        svc.brand_briefs_dir = temp_brand_briefs_dir
        return svc

    @pytest.mark.asyncio
    async def test_find_brand_brief(self, service):
        """Test finding brand brief by company name."""
        result = service._find_brand_brief("TechCorp")

        assert result is not None
        assert "techcorp" in str(result).lower()

    @pytest.mark.asyncio
    async def test_find_brand_brief_not_found(self, service):
        """Test finding brand brief that doesn't exist."""
        result = service._find_brand_brief("NonexistentCompany")

        assert result is None

    @pytest.mark.asyncio
    async def test_link_brand_brief_manually(self, service, sample_prospect):
        """Test manually linking a brand brief."""
        result = await service.link_brand_brief(
            sample_prospect.id,
            "/path/to/brief.md",
        )

        assert result.brand_brief_path == "/path/to/brief.md"


class TestProspectQueries:
    """Tests for prospect query methods."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    @pytest.mark.asyncio
    async def test_get_prospects_for_outreach_linkedin(
        self, service, sample_campaign
    ):
        """Test getting prospects for LinkedIn outreach."""
        # Create prospects with and without LinkedIn
        await service.create_prospect(
            campaign_id=sample_campaign.id,
            first_name="With",
            last_name="LinkedIn",
            linkedin_url="https://linkedin.com/in/test",
        )
        await service.create_prospect(
            campaign_id=sample_campaign.id,
            first_name="Without",
            last_name="LinkedIn",
        )

        prospects = await service.get_prospects_for_outreach(
            sample_campaign.id,
            channel="linkedin",
            limit=10,
        )

        assert all(p.linkedin_url is not None for p in prospects)

    @pytest.mark.asyncio
    async def test_get_prospects_for_outreach_email(
        self, service, sample_campaign
    ):
        """Test getting prospects for email outreach."""
        await service.create_prospect(
            campaign_id=sample_campaign.id,
            first_name="With",
            last_name="Email",
            email="test@example.com",
        )
        await service.create_prospect(
            campaign_id=sample_campaign.id,
            first_name="Without",
            last_name="Email",
        )

        prospects = await service.get_prospects_for_outreach(
            sample_campaign.id,
            channel="email",
            limit=10,
        )

        assert all(p.email is not None for p in prospects)

    @pytest.mark.asyncio
    async def test_get_prospect_timeline(self, service, sample_prospect):
        """Test getting prospect timeline."""
        timeline = await service.get_prospect_timeline(sample_prospect.id)

        assert len(timeline) >= 1
        # First event should be creation
        assert timeline[0]["event_type"] == "created"

    @pytest.mark.asyncio
    async def test_get_message_count(self, service, sample_prospect, sample_message):
        """Test getting message count for prospect."""
        count = await service.get_message_count(sample_prospect.id)

        assert count >= 1


class TestEmailValidation:
    """Tests for email validation."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    def test_valid_email(self, service):
        """Test valid email addresses."""
        assert service._is_valid_email("test@example.com") is True
        assert service._is_valid_email("user.name@domain.co.uk") is True
        assert service._is_valid_email("user+tag@example.org") is True

    def test_invalid_email(self, service):
        """Test invalid email addresses."""
        assert service._is_valid_email("not-an-email") is False
        assert service._is_valid_email("missing@domain") is False
        assert service._is_valid_email("@nodomain.com") is False
        assert service._is_valid_email("") is False


class TestCheckDuplicate:
    """Tests for check_duplicate method."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    @pytest.mark.asyncio
    async def test_duplicate_by_email(self, service, sample_prospect, sample_campaign):
        """Test duplicate detection by email."""
        is_duplicate = await service.check_duplicate(
            campaign_id=sample_campaign.id,
            email=sample_prospect.email,
            linkedin_url=None,
        )

        assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_duplicate_by_linkedin(self, service, sample_prospect, sample_campaign):
        """Test duplicate detection by LinkedIn URL."""
        is_duplicate = await service.check_duplicate(
            campaign_id=sample_campaign.id,
            email=None,
            linkedin_url=sample_prospect.linkedin_url,
        )

        assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_no_duplicate(self, service, sample_campaign):
        """Test no duplicate found."""
        is_duplicate = await service.check_duplicate(
            campaign_id=sample_campaign.id,
            email="new@example.com",
            linkedin_url="https://linkedin.com/in/newuser",
        )

        assert is_duplicate is False

    @pytest.mark.asyncio
    async def test_no_identifiers(self, service, sample_campaign):
        """Test with no identifiers."""
        is_duplicate = await service.check_duplicate(
            campaign_id=sample_campaign.id,
            email=None,
            linkedin_url=None,
        )

        assert is_duplicate is False


class TestNormalizeCompanyName:
    """Tests for _normalize_company_name method."""

    @pytest_asyncio.fixture
    async def service(self, db_session):
        return ProspectService(db_session)

    def test_remove_inc(self, service):
        """Test removing 'Inc' suffix."""
        result = service._normalize_company_name("Acme Inc")
        assert result == "acme"

    def test_remove_llc(self, service):
        """Test removing 'LLC' suffix."""
        result = service._normalize_company_name("Tech LLC")
        assert result == "tech"

    def test_remove_corp(self, service):
        """Test removing 'Corp' suffix."""
        result = service._normalize_company_name("Global Corp")
        assert result == "global"

    def test_lowercase_and_normalize(self, service):
        """Test lowercase and special char removal."""
        result = service._normalize_company_name("Tech-Corp & Associates")
        assert result == "techcorpassociates"
