"""
Unit tests for BrandBriefLoader service.

Tests cover:
- Loading brand briefs from file paths
- Searching by company name
- Parsing markdown sections
- Extracting personalization context
- ICP type detection
- Decision maker extraction
"""

import tempfile
from pathlib import Path

import pytest

from api.services.brand_brief_loader import BrandBriefLoader, get_brand_brief_loader


class TestBrandBriefLoaderFactory:
    """Test factory function."""

    def test_get_brand_brief_loader(self):
        """Test factory returns BrandBriefLoader instance."""
        loader = get_brand_brief_loader()
        assert isinstance(loader, BrandBriefLoader)

    def test_factory_with_custom_dir(self, tmp_path):
        """Test factory with custom directory."""
        loader = get_brand_brief_loader(tmp_path)
        assert loader.brand_briefs_dir == tmp_path


class TestLoadBrief:
    """Tests for load_brief method."""

    @pytest.fixture
    def loader(self, temp_brand_briefs_dir):
        return BrandBriefLoader(temp_brand_briefs_dir)

    def test_load_existing_brief(self, loader, temp_brand_briefs_dir):
        """Test loading an existing brand brief."""
        brief_path = temp_brand_briefs_dir / "technology" / "techcorp.md"
        result = loader.load_brief(brief_path)

        assert result is not None
        assert result["file_path"] == str(brief_path)
        assert "company_overview" in result

    def test_load_brief_not_found(self, loader):
        """Test loading non-existent brief raises error."""
        with pytest.raises(FileNotFoundError):
            loader.load_brief("/nonexistent/path/brief.md")

    def test_load_relative_path(self, loader, temp_brand_briefs_dir):
        """Test loading with relative path."""
        result = loader.load_brief("technology/techcorp.md")

        assert result is not None
        assert "company_overview" in result


class TestSearchByCompany:
    """Tests for search_by_company method."""

    @pytest.fixture
    def loader(self, temp_brand_briefs_dir):
        return BrandBriefLoader(temp_brand_briefs_dir)

    def test_search_exact_match(self, loader):
        """Test searching with exact company name."""
        result = loader.search_by_company("TechCorp")

        assert result is not None
        assert result["company_overview"]["company_name"] == "TechCorp"

    def test_search_case_insensitive(self, loader):
        """Test search is case insensitive."""
        result = loader.search_by_company("techcorp")

        assert result is not None
        assert result["company_overview"]["company_name"] == "TechCorp"

    def test_search_partial_match(self, loader):
        """Test partial company name match."""
        result = loader.search_by_company("Tech")

        assert result is not None

    def test_search_with_suffix(self, loader):
        """Test search strips common suffixes."""
        result = loader.search_by_company("TechCorp Inc")

        assert result is not None

    def test_search_not_found(self, loader):
        """Test search returns None when not found."""
        result = loader.search_by_company("NonexistentCompany")

        assert result is None

    def test_search_missing_directory(self):
        """Test search with missing directory."""
        loader = BrandBriefLoader(Path("/nonexistent/directory"))
        result = loader.search_by_company("AnyCompany")

        assert result is None


class TestListBriefs:
    """Tests for list_briefs method."""

    @pytest.fixture
    def loader(self, temp_brand_briefs_dir):
        return BrandBriefLoader(temp_brand_briefs_dir)

    def test_list_briefs(self, loader):
        """Test listing all briefs."""
        briefs = loader.list_briefs()

        assert len(briefs) >= 1
        assert all("path" in b for b in briefs)
        assert all("company_name" in b for b in briefs)
        assert all("industry" in b for b in briefs)

    def test_list_briefs_sorted(self, loader):
        """Test briefs are sorted by company name."""
        briefs = loader.list_briefs()

        if len(briefs) > 1:
            names = [b["company_name"] for b in briefs]
            assert names == sorted(names)

    def test_list_briefs_missing_directory(self):
        """Test listing with missing directory."""
        loader = BrandBriefLoader(Path("/nonexistent/directory"))
        briefs = loader.list_briefs()

        assert briefs == []


class TestParseBrief:
    """Tests for _parse_brief method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_parse_company_overview(self, loader, sample_brand_brief_content):
        """Test parsing company overview section."""
        result = loader._parse_brief(sample_brand_brief_content, "test.md")

        assert result["company_overview"]["company_name"] == "TechCorp"
        assert result["company_overview"]["industry"] == "SaaS / Technology"
        assert result["company_overview"]["revenue"] == "$5M ARR"
        assert result["company_overview"]["employees"] == "50"

    def test_parse_tier_and_score(self, loader, sample_brand_brief_content):
        """Test parsing tier and score."""
        result = loader._parse_brief(sample_brand_brief_content, "test.md")

        assert result["tier"] == 2
        assert result["score"]["value"] == 85
        assert result["score"]["max"] == 100

    def test_parse_pain_points(self, loader, sample_brand_brief_content):
        """Test parsing key pain points."""
        result = loader._parse_brief(sample_brand_brief_content, "test.md")

        assert len(result["key_pain_points"]) >= 3
        assert any("Manual Content Moderation" in pp for pp in result["key_pain_points"])

    def test_parse_opportunities(self, loader, sample_brand_brief_content):
        """Test parsing key opportunities."""
        result = loader._parse_brief(sample_brand_brief_content, "test.md")

        assert len(result["key_opportunities"]) >= 1

    def test_parse_decision_makers(self, loader, sample_brand_brief_content):
        """Test parsing decision makers."""
        result = loader._parse_brief(sample_brand_brief_content, "test.md")

        assert len(result["decision_makers"]) >= 1
        assert any(dm["role"] == "CEO" for dm in result["decision_makers"])

    def test_parse_messaging_strategy(self, loader, sample_brand_brief_content):
        """Test parsing messaging strategy."""
        result = loader._parse_brief(sample_brand_brief_content, "test.md")

        assert "value_propositions" in result["messaging_strategy"]
        assert len(result["messaging_strategy"]["value_propositions"]) >= 1

    def test_parse_sample_outreach(self, loader, sample_brand_brief_content):
        """Test parsing sample outreach."""
        result = loader._parse_brief(sample_brand_brief_content, "test.md")

        assert "subject" in result["sample_outreach"]
        assert result["sample_outreach"]["subject"] != ""


class TestSplitSections:
    """Tests for _split_sections method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_split_h2_sections(self, loader):
        """Test splitting by ## headers."""
        content = """## Section One
Content for section one.

## Section Two
Content for section two.
"""
        sections = loader._split_sections(content)

        assert "Section One" in sections
        assert "Section Two" in sections

    def test_split_h3_sections(self, loader):
        """Test splitting by ### headers."""
        content = """### Subsection A
Content A.

### Subsection B
Content B.
"""
        sections = loader._split_sections(content)

        assert "Subsection A" in sections
        assert "Subsection B" in sections

    def test_preserves_content(self, loader):
        """Test section content is preserved."""
        content = """## My Section
Line 1
Line 2
Line 3
"""
        sections = loader._split_sections(content)

        assert "Line 1" in sections["My Section"]
        assert "Line 2" in sections["My Section"]


class TestParseOverviewTable:
    """Tests for _parse_overview_table method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_parse_table(self, loader):
        """Test parsing markdown table."""
        content = """
| **Field** | Details |
|-----------|---------|
| **Company Name** | TestCo |
| **Industry** | Tech |
| **Revenue** | $10M |
"""
        result = loader._parse_overview_table(content)

        assert result["company_name"] == "TestCo"
        assert result["industry"] == "Tech"
        assert result["revenue"] == "$10M"

    def test_skip_header_row(self, loader):
        """Test header row is skipped."""
        content = """
| Field | Details |
|-------|---------|
| **Name** | Test |
"""
        result = loader._parse_overview_table(content)

        assert "field" not in result


class TestParseNumberedList:
    """Tests for _parse_numbered_list method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_parse_numbered_list(self, loader):
        """Test parsing numbered list."""
        content = """
1. First item - Description of first
2. Second item - Description of second
3. Third item
"""
        result = loader._parse_numbered_list(content)

        assert len(result) == 3
        assert "First item" in result[0]

    def test_parse_bold_items(self, loader):
        """Test parsing numbered list with bold."""
        content = """
1. **Bold Item** - With description
2. **Another Bold** - More info
"""
        result = loader._parse_numbered_list(content)

        assert len(result) == 2
        assert "Bold Item" in result[0]


class TestParseBulletList:
    """Tests for _parse_bullet_list method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_parse_dash_bullets(self, loader):
        """Test parsing dash bullet points."""
        content = """
- First bullet
- Second bullet
- Third bullet
"""
        result = loader._parse_bullet_list(content)

        assert len(result) == 3
        assert "First bullet" in result[0]

    def test_parse_asterisk_bullets(self, loader):
        """Test parsing asterisk bullet points."""
        content = """
* First bullet
* Second bullet
"""
        result = loader._parse_bullet_list(content)

        assert len(result) == 2


class TestParseDecisionMakers:
    """Tests for _parse_decision_makers method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_parse_decision_makers_table(self, loader):
        """Test parsing decision makers table."""
        content = """
| Role | Search Strategy | Priority |
|------|-----------------|----------|
| CEO | Direct outreach | HIGH |
| CTO | LinkedIn connection | MEDIUM |
"""
        result = loader._parse_decision_makers(content)

        assert len(result) == 2
        assert result[0]["role"] == "CEO"
        assert result[0]["priority"] == "HIGH"
        assert result[1]["role"] == "CTO"


class TestGetPersonalizationContext:
    """Tests for get_personalization_context method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    @pytest.fixture
    def sample_brief(self, loader, sample_brand_brief_content):
        return loader._parse_brief(sample_brand_brief_content, "test.md")

    def test_extract_company_info(self, loader, sample_brief):
        """Test extracting company info."""
        context = loader.get_personalization_context(sample_brief)

        assert context["company_name"] == "TechCorp"
        assert "SaaS" in context["industry"] or "Technology" in context["industry"]

    def test_extract_pain_points(self, loader, sample_brief):
        """Test extracting pain points (top 3)."""
        context = loader.get_personalization_context(sample_brief)

        assert len(context["pain_points"]) <= 3
        assert len(context["pain_points"]) >= 1

    def test_role_specific_value_prop(self, loader, sample_brief):
        """Test role-specific value proposition."""
        context = loader.get_personalization_context(sample_brief, prospect_role="CEO")

        assert context["value_proposition"] != ""

    def test_fallback_value_prop(self, loader, sample_brief):
        """Test fallback value proposition when no role match."""
        context = loader.get_personalization_context(sample_brief, prospect_role="Unknown Role")

        assert context["value_proposition"] != ""

    def test_extract_decision_makers(self, loader, sample_brief):
        """Test extracting decision makers."""
        context = loader.get_personalization_context(sample_brief)

        assert len(context["decision_makers"]) >= 1


class TestExtractPainPoints:
    """Tests for extract_pain_points method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_extract_pain_points(self, loader):
        """Test extracting pain points from brief."""
        brief = {"key_pain_points": ["Point 1", "Point 2", "Point 3"]}
        result = loader.extract_pain_points(brief)

        assert result == ["Point 1", "Point 2", "Point 3"]

    def test_empty_pain_points(self, loader):
        """Test empty pain points."""
        brief = {}
        result = loader.extract_pain_points(brief)

        assert result == []


class TestExtractMetrics:
    """Tests for extract_metrics method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_extract_overview_metrics(self, loader):
        """Test extracting metrics from company overview."""
        brief = {
            "company_overview": {
                "revenue": "$5M",
                "employees": "50",
            },
            "digital_presence": {"metrics": {}},
        }
        result = loader.extract_metrics(brief)

        assert result["revenue"] == "$5M"
        assert result["employees"] == "50"

    def test_extract_digital_metrics(self, loader):
        """Test extracting digital presence metrics."""
        brief = {
            "company_overview": {},
            "digital_presence": {
                "metrics": {
                    "website_traffic": "50K/month",
                    "social_followers": "10K",
                }
            },
        }
        result = loader.extract_metrics(brief)

        assert result["website_traffic"] == "50K/month"


class TestGetICPType:
    """Tests for get_icp_type method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_enterprise_by_tier(self, loader):
        """Test enterprise ICP by tier."""
        brief = {"tier": 1, "company_overview": {}}
        result = loader.get_icp_type(brief)
        assert result == "enterprise"

        brief = {"tier": 2, "company_overview": {}}
        result = loader.get_icp_type(brief)
        assert result == "enterprise"

    def test_solopreneur_by_tier(self, loader):
        """Test solopreneur ICP by tier."""
        brief = {"tier": 4, "company_overview": {}}
        result = loader.get_icp_type(brief)
        assert result == "solopreneur"

    def test_enterprise_by_revenue_billion(self, loader):
        """Test enterprise ICP by billion revenue."""
        brief = {
            "tier": None,
            "company_overview": {"revenue": "$1B"},
        }
        result = loader.get_icp_type(brief)
        assert result == "enterprise"

    def test_enterprise_by_revenue_high_million(self, loader):
        """Test enterprise ICP by high million revenue."""
        brief = {
            "tier": None,
            "company_overview": {"revenue": "$100M ARR"},
        }
        result = loader.get_icp_type(brief)
        assert result == "enterprise"

    def test_sme_by_revenue(self, loader):
        """Test SME ICP by revenue."""
        brief = {
            "tier": None,
            "company_overview": {"revenue": "$5M"},
        }
        result = loader.get_icp_type(brief)
        assert result == "sme"

    def test_enterprise_by_employees(self, loader):
        """Test enterprise ICP by employee count."""
        brief = {
            "tier": None,
            "company_overview": {"employees": "500"},
        }
        result = loader.get_icp_type(brief)
        assert result == "enterprise"

    def test_sme_by_employees(self, loader):
        """Test SME ICP by employee count."""
        brief = {
            "tier": None,
            "company_overview": {"employees": "50"},
        }
        result = loader.get_icp_type(brief)
        assert result == "sme"

    def test_solopreneur_by_employees(self, loader):
        """Test solopreneur ICP by low employee count."""
        brief = {
            "tier": None,
            "company_overview": {"employees": "5"},
        }
        result = loader.get_icp_type(brief)
        assert result == "solopreneur"

    def test_default_sme(self, loader):
        """Test default to SME when no indicators."""
        brief = {"tier": None, "company_overview": {}}
        result = loader.get_icp_type(brief)
        assert result == "sme"


class TestNormalizeName:
    """Tests for _normalize_name method."""

    @pytest.fixture
    def loader(self):
        return BrandBriefLoader()

    def test_remove_inc_suffix(self, loader):
        """Test removing 'Inc' suffix."""
        result = loader._normalize_name("Acme Inc")
        assert result == "acme"

    def test_remove_llc_suffix(self, loader):
        """Test removing 'LLC' suffix."""
        result = loader._normalize_name("TechCorp LLC")
        assert result == "techcorp"

    def test_remove_ltd_suffix(self, loader):
        """Test removing 'Ltd' suffix."""
        result = loader._normalize_name("Global Ltd")
        assert result == "global"

    def test_lowercase(self, loader):
        """Test conversion to lowercase."""
        result = loader._normalize_name("TechCorp")
        assert result == "techcorp"

    def test_remove_special_chars(self, loader):
        """Test removing special characters."""
        result = loader._normalize_name("Tech-Corp & Associates")
        assert result == "techcorpassociates"

    def test_remove_latam_global(self, loader):
        """Test removing 'latam' and 'global' suffixes."""
        result = loader._normalize_name("Company LATAM")
        assert result == "company"

        result = loader._normalize_name("Company Global")
        assert result == "company"
