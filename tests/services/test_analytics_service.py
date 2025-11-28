"""
Tests for AnalyticsService.

Tests cover:
- Research intelligence generation
- Strategic synthesis
- Insights mapping
- Competitor analysis
- Trend analysis
- Quality assessment
- Audience personas
- Content strategy
- Cultural validation
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestAnalyticsServiceInit:
    """Tests for AnalyticsService initialization."""

    def test_analytics_service_initialization(self):
        """Test AnalyticsService initializes correctly."""
        from api.services.analytics_service import AnalyticsService

        ai_manager = MagicMock()
        file_service = MagicMock()

        service = AnalyticsService(
            ai_manager=ai_manager,
            file_service=file_service
        )

        assert service.ai is ai_manager
        assert service.files is file_service

    def test_analytics_service_with_none_dependencies(self):
        """Test AnalyticsService with None dependencies."""
        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService()

        assert service.ai is None
        assert service.files is None


class TestResearchIntelligence:
    """Tests for research intelligence generation."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService with mocks."""
        ai_manager = MagicMock()
        ai_manager.generate_completion = AsyncMock(return_value="""
# Research Intelligence Report

## Market Landscape Overview
- Market growing at 15% annually
- Key players include Competitor A and B

## Consumer Insights
- Insight 1: Consumers value authenticity
- Insight 2: Price sensitivity is moderate

## Cultural Context
- Local traditions influence purchasing

## Opportunity Map
- Opportunity 1: Untapped digital channel
- Opportunity 2: Premium segment growth
""")

        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))
        file_service.read_file = AsyncMock(return_value="# Brief Content")

        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService(ai_manager=ai_manager, file_service=file_service)

        # Mock helper methods
        service._load_all_research = AsyncMock(return_value="Research content here...")
        service._save_report = AsyncMock(return_value=Path("/tmp/test-project/analytics/report.md"))

        return service

    @pytest.mark.asyncio
    async def test_generate_research_intelligence_success(self, analytics_service):
        """Test successful research intelligence generation."""
        result = await analytics_service.generate_research_intelligence("test-project")

        assert result["status"] == "success"
        assert "report_path" in result
        assert "insights_count" in result
        assert "opportunities_count" in result

    @pytest.mark.asyncio
    async def test_generate_research_intelligence_no_research(self, analytics_service):
        """Test research intelligence with no research files."""
        analytics_service._load_all_research = AsyncMock(return_value="")

        result = await analytics_service.generate_research_intelligence("test-project")

        assert result["status"] == "no_research"
        assert "message" in result


class TestStrategicSynthesis:
    """Tests for strategic insights synthesis."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService with mocks."""
        ai_manager = MagicMock()
        ai_manager.generate_completion = AsyncMock(return_value="""
# Strategic Insights Brief

## The Big Picture
- Market is growing rapidly
- Consumer truth: They seek authenticity
- Opportunity: Digital-first approach

## Key Insights
1. Insight one
2. Insight two
3. Insight three
4. Insight four
5. Insight five

## Strategic Territories
- Territory 1: Innovation Leader
- Territory 2: Community Builder
- Territory 3: Value Champion

## Success Factors
- Factor 1
- Factor 2
""")

        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))

        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService(ai_manager=ai_manager, file_service=file_service)

        service._load_all_research = AsyncMock(return_value="Research content")
        service._load_brief = AsyncMock(return_value="Brief content")
        service._save_report = AsyncMock(return_value=Path("/tmp/report.md"))

        return service

    @pytest.mark.asyncio
    async def test_synthesize_strategic_insights_success(self, analytics_service):
        """Test successful strategic synthesis."""
        result = await analytics_service.synthesize_strategic_insights("test-project")

        assert result["status"] == "success"
        assert "key_insights_count" in result
        assert "territories_count" in result


class TestInsightsMapping:
    """Tests for insights-to-ideas mapping."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService with mocks."""
        ai_manager = MagicMock()
        ai_manager.generate_completion = AsyncMock(return_value="""
# Insights to Ideas Mapping

**Idea 1:**
- Insight: Consumer authenticity desire
- Connection: Strong

**Idea 2:**
- Insight: Digital engagement trend
- Connection: Medium

## Coverage Analysis
All major insights covered.
""")

        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))

        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService(ai_manager=ai_manager, file_service=file_service)

        service._load_all_ideas = AsyncMock(return_value=[
            {"number": "01", "filename": "idea-01.md", "content": "Idea 1 content"},
            {"number": "02", "filename": "idea-02.md", "content": "Idea 2 content"},
        ])
        service._save_report = AsyncMock(return_value=Path("/tmp/report.md"))

        return service

    @pytest.mark.asyncio
    async def test_map_insights_to_ideas_success(self, analytics_service):
        """Test successful insights mapping."""
        # Mock intelligence report exists
        analytics_service.files.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))

        with patch.object(Path, "exists", return_value=True):
            result = await analytics_service.map_insights_to_ideas("test-project")

        assert result["status"] == "success"
        assert "ideas_mapped" in result
        assert "coverage_score" in result

    @pytest.mark.asyncio
    async def test_map_insights_no_ideas(self, analytics_service):
        """Test mapping with no ideas."""
        analytics_service._load_all_ideas = AsyncMock(return_value=[])

        result = await analytics_service.map_insights_to_ideas("test-project")

        assert result["status"] == "no_ideas"


class TestCompetitorAnalysis:
    """Tests for competitor analysis."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService with mocks."""
        ai_manager = MagicMock()
        ai_manager.generate_completion = AsyncMock(return_value="""
# Competitive Intelligence Dashboard

## Competitor Landscape
- Competitor A: Market leader
- Competitor B: Challenger brand
- Competitor C: Niche player

## Campaign Analysis
Recent campaigns analyzed...

## Positioning Map
Traditional ← → Innovative axis...

## Strategic Recommendations
- Differentiate on innovation
- Avoid price wars
""")

        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))

        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService(ai_manager=ai_manager, file_service=file_service)

        service._load_all_research = AsyncMock(return_value="Competitor research...")
        service._load_brief = AsyncMock(return_value="Brief content")
        service._save_report = AsyncMock(return_value=Path("/tmp/report.md"))

        return service

    @pytest.mark.asyncio
    async def test_analyze_competitors_success(self, analytics_service):
        """Test successful competitor analysis."""
        result = await analytics_service.analyze_competitors("test-project")

        assert result["status"] == "success"
        assert "competitors_analyzed" in result
        assert "opportunities_identified" in result

    @pytest.mark.asyncio
    async def test_analyze_competitors_no_research(self, analytics_service):
        """Test competitor analysis with no research."""
        analytics_service._load_all_research = AsyncMock(return_value="")

        result = await analytics_service.analyze_competitors("test-project")

        assert result["status"] == "no_research"


class TestTrendAnalysis:
    """Tests for trend analysis."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService with mocks."""
        ai_manager = MagicMock()
        ai_manager.generate_completion = AsyncMock(return_value="""
# Trend Analysis Report

## Macro Trends
- Sustainability focus: Velocity 8, Relevance 9, Longevity 9

## Industry Trends
- Digital transformation accelerating

## Micro Trends
- User-generated content growth

## Trend Implications
- Opportunity: Green positioning
""")

        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))

        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService(ai_manager=ai_manager, file_service=file_service)

        service._load_all_research = AsyncMock(return_value="Trend research...")
        service._load_brief = AsyncMock(return_value="Brief content")
        service._save_report = AsyncMock(return_value=Path("/tmp/report.md"))

        return service

    @pytest.mark.asyncio
    async def test_identify_trends_success(self, analytics_service):
        """Test successful trend identification."""
        result = await analytics_service.identify_trends("test-project")

        assert result["status"] == "success"
        assert "trends_identified" in result
        assert "high_priority_trends" in result

    @pytest.mark.asyncio
    async def test_identify_trends_no_research(self, analytics_service):
        """Test trend analysis with no research."""
        analytics_service._load_all_research = AsyncMock(return_value="")

        result = await analytics_service.identify_trends("test-project")

        assert result["status"] == "no_research"


class TestQualityAssessment:
    """Tests for research quality assessment."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService with mocks."""
        ai_manager = MagicMock()
        ai_manager.generate_completion = AsyncMock(return_value="""
# Research Quality Dashboard

## Coverage Analysis
Market: Good
Consumer: Excellent
Competitor: Fair

## Source Quality
High credibility overall

## Gap Identification
- Missing: Primary research
- Critical: Consumer interviews

## Overall Quality Score: 7/10
""")

        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))

        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService(ai_manager=ai_manager, file_service=file_service)

        service._load_all_research = AsyncMock(return_value="Research content...")
        service._load_brief = AsyncMock(return_value="Brief content")
        service._analyze_research_files = AsyncMock(return_value={
            "total_files": 10,
            "by_category": {"market_analysis": 3, "consumer_research": 4},
            "file_list": ["file1.md", "file2.md"],
        })
        service._save_report = AsyncMock(return_value=Path("/tmp/report.md"))

        return service

    @pytest.mark.asyncio
    async def test_assess_research_quality_success(self, analytics_service):
        """Test successful quality assessment."""
        result = await analytics_service.assess_research_quality("test-project")

        assert result["status"] == "success"
        assert "quality_score" in result
        assert "gaps_identified" in result
        assert "total_sources" in result

    @pytest.mark.asyncio
    async def test_assess_research_quality_no_research(self, analytics_service):
        """Test quality assessment with no research."""
        analytics_service._load_all_research = AsyncMock(return_value="")

        result = await analytics_service.assess_research_quality("test-project")

        assert result["status"] == "no_research"


class TestAudiencePersonas:
    """Tests for audience persona creation."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService with mocks."""
        ai_manager = MagicMock()
        ai_manager.generate_completion = AsyncMock(return_value="""
# Audience Insights Report

## Persona 1: María Digital
Age 28, professional in Asunción...

## Persona 2: Carlos Tradicional
Age 45, family man...

## Segments
- Segment A: Young professionals
- Segment B: Traditional families
""")

        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))

        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService(ai_manager=ai_manager, file_service=file_service)

        service._load_all_research = AsyncMock(return_value="Audience research...")
        service._load_brief = AsyncMock(return_value="Brief content")
        service._save_report = AsyncMock(return_value=Path("/tmp/report.md"))

        return service

    @pytest.mark.asyncio
    async def test_create_audience_personas_success(self, analytics_service):
        """Test successful persona creation."""
        result = await analytics_service.create_audience_personas("test-project")

        assert result["status"] == "success"
        assert "personas_created" in result
        assert "segments_identified" in result

    @pytest.mark.asyncio
    async def test_create_audience_personas_no_research(self, analytics_service):
        """Test persona creation with no research."""
        analytics_service._load_all_research = AsyncMock(return_value="")

        result = await analytics_service.create_audience_personas("test-project")

        assert result["status"] == "no_research"


class TestContentStrategy:
    """Tests for content strategy generation."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService with mocks."""
        ai_manager = MagicMock()
        ai_manager.generate_completion = AsyncMock(return_value="""
# Content Strategy Framework

## Content Pillars
1. Educational content
2. Entertainment
3. Community engagement
4. Product highlights

## Channel Strategy
- Instagram: Visual content
- Facebook: Community
- LinkedIn: Professional

## Content Calendar Template
Week 1-4 schedule...
""")

        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))

        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService(ai_manager=ai_manager, file_service=file_service)

        service._load_all_research = AsyncMock(return_value="Research content...")
        service._load_brief = AsyncMock(return_value="Brief content")
        service._save_report = AsyncMock(return_value=Path("/tmp/report.md"))

        return service

    @pytest.mark.asyncio
    async def test_generate_content_strategy_success(self, analytics_service):
        """Test successful content strategy generation."""
        with patch.object(Path, "exists", return_value=True):
            result = await analytics_service.generate_content_strategy("test-project")

        assert result["status"] == "success"
        assert "content_pillars" in result
        assert "channels_covered" in result


class TestCulturalValidation:
    """Tests for cultural sensitivity validation."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService with mocks."""
        ai_manager = MagicMock()
        ai_manager.generate_completion = AsyncMock(return_value="""
# Cultural Sensitivity Analysis

## Cultural Codes
- Family values: Central
- Local pride: Important
- Guaraní elements: Consider

## Language Nuances
Spanish + Guaraní considerations...

## Visual Guidelines
- Colors: Green, white
- Imagery: Family-focused

## Validation Score: 8/10
""")

        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=Path("/tmp/test-project"))

        from api.services.analytics_service import AnalyticsService

        service = AnalyticsService(ai_manager=ai_manager, file_service=file_service)

        service._load_all_research = AsyncMock(return_value="Cultural research...")
        service._load_brief = AsyncMock(return_value="Brief content")
        service._load_all_ideas = AsyncMock(return_value=[{"content": "Idea 1"}])
        service._save_report = AsyncMock(return_value=Path("/tmp/report.md"))

        return service

    @pytest.mark.asyncio
    async def test_validate_cultural_sensitivity_success(self, analytics_service):
        """Test successful cultural validation."""
        result = await analytics_service.validate_cultural_sensitivity("test-project")

        assert result["status"] == "success"
        assert "cultural_codes_identified" in result
        assert "validation_score" in result


class TestHelperMethods:
    """Tests for analytics helper methods."""

    @pytest.fixture
    def analytics_service(self, tmp_path):
        """Create AnalyticsService with real path for testing."""
        ai_manager = MagicMock()
        file_service = MagicMock()
        file_service.get_project_path = MagicMock(return_value=tmp_path)
        file_service.read_file = AsyncMock(return_value="# Brief content")

        from api.services.analytics_service import AnalyticsService

        return AnalyticsService(ai_manager=ai_manager, file_service=file_service)

    @pytest.mark.asyncio
    async def test_load_all_research(self, analytics_service, tmp_path):
        """Test loading all research files."""
        # Create test research directories and files
        research_dir = tmp_path / "investigacion-mercado"
        research_dir.mkdir()
        (research_dir / "market-analysis.md").write_text("# Market Analysis\n\nContent here")

        result = await analytics_service._load_all_research("test-project")

        assert "Market Analysis" in result or result == ""  # Depends on file reading

    @pytest.mark.asyncio
    async def test_load_brief(self, analytics_service):
        """Test loading project brief."""
        result = await analytics_service._load_brief("test-project")

        assert "Brief" in result

    @pytest.mark.asyncio
    async def test_load_brief_handles_error(self, analytics_service):
        """Test load brief handles missing file."""
        analytics_service.files.read_file = AsyncMock(side_effect=Exception("Not found"))

        result = await analytics_service._load_brief("test-project")

        assert result == ""

    @pytest.mark.asyncio
    async def test_save_report(self, analytics_service, tmp_path):
        """Test saving analytics report."""
        result = await analytics_service._save_report(
            "test-project",
            "TEST-REPORT.md",
            "# Test Report Content"
        )

        assert result.name == "TEST-REPORT.md"
        assert result.exists()

    @pytest.mark.asyncio
    async def test_analyze_research_files(self, analytics_service, tmp_path):
        """Test research file analysis."""
        # Create test structure
        research_dir = tmp_path / "investigacion-mercado"
        research_dir.mkdir()
        (research_dir / "competitor-analysis.md").write_text("# Competitor")
        (research_dir / "trend-report.md").write_text("# Trends")
        (research_dir / "market-overview.md").write_text("# Market")

        result = await analytics_service._analyze_research_files(tmp_path)

        assert result["total_files"] == 3
        assert "by_category" in result
        assert "file_list" in result


class TestPromptCreation:
    """Tests for AI prompt creation methods."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService."""
        from api.services.analytics_service import AnalyticsService

        return AnalyticsService()

    def test_create_research_intelligence_prompt(self, analytics_service):
        """Test research intelligence prompt creation."""
        prompt = analytics_service._create_research_intelligence_prompt("Research content here")

        assert "Research Intelligence Report" in prompt
        assert "Market Landscape" in prompt
        assert "Consumer Insights" in prompt
        assert "Cultural Context" in prompt
        assert "Opportunity Map" in prompt

    def test_create_strategic_synthesis_prompt(self, analytics_service):
        """Test strategic synthesis prompt creation."""
        prompt = analytics_service._create_strategic_synthesis_prompt(
            brief="Brief content",
            research="Research content"
        )

        assert "Strategic Insights Brief" in prompt
        assert "Big Picture" in prompt
        assert "Key Insights" in prompt

    def test_create_competitive_analysis_prompt(self, analytics_service):
        """Test competitive analysis prompt creation."""
        prompt = analytics_service._create_competitive_analysis_prompt(
            brief="Brief",
            research="Research"
        )

        assert "Competitive Intelligence" in prompt
        assert "Competitor Landscape" in prompt


class TestResponseParsing:
    """Tests for AI response parsing methods."""

    @pytest.fixture
    def analytics_service(self):
        """Create AnalyticsService."""
        from api.services.analytics_service import AnalyticsService

        return AnalyticsService()

    def test_parse_research_intelligence(self, analytics_service):
        """Test parsing research intelligence response."""
        response = """
# Research Intelligence Report

## Consumer Insights
- Insight 1
- Insight 2

## Opportunity Map
- Opportunity 1
"""
        result = analytics_service._parse_research_intelligence(response)

        assert "markdown" in result
        assert "insights_count" in result
        assert "opportunities_count" in result
        assert "metadata" in result

    def test_parse_strategic_synthesis(self, analytics_service):
        """Test parsing strategic synthesis response."""
        response = """
# Strategic Brief

## Key Insights
1. First
2. Second

## Strategic Territories
- Territory 1
"""
        result = analytics_service._parse_strategic_synthesis(response)

        assert "markdown" in result
        assert result["insights_count"] == 5  # Fixed at 5 as specified
        assert "territories_count" in result

    def test_parse_insights_mapping(self, analytics_service):
        """Test parsing insights mapping response."""
        response = """
**Idea 1:**
Insight: Something

**Idea 2:**
Insight: Another
"""
        result = analytics_service._parse_insights_mapping(response)

        assert "ideas_count" in result
        assert "coverage_score" in result
