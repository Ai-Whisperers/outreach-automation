"""
Service tests for ideas service module.

Tests cover:
- Idea generation
- Idea expansion
- Quality validation
- Cultural validation
- Scoring and ranking
- Tier classification
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestIdeasServiceInitialization:
    """Tests for IdeasService initialization."""

    def test_service_initialization(self):
        """Test service initializes with dependencies."""
        with patch("api.services.ideas_service.get_ai_manager"):
            with patch("api.services.ideas_service.get_prompt_loader"):
                with patch("api.services.ideas_service.get_file_service"):
                    with patch("api.services.ideas_service.get_template_renderer"):
                        with patch("api.services.ideas_service.get_research_service"):
                            with patch("api.services.ideas_service.get_settings"):
                                from api.services.ideas_service import IdeasService

                                service = IdeasService()

                                assert service.ai is not None
                                assert service.prompts is not None
                                assert service.files is not None


class TestIdeaGeneration:
    """Tests for idea generation."""

    @pytest.fixture
    def service(self):
        """Create ideas service with mocked dependencies."""
        with patch("api.services.ideas_service.get_ai_manager") as mock_ai:
            with patch("api.services.ideas_service.get_prompt_loader") as mock_prompts:
                with patch("api.services.ideas_service.get_file_service") as mock_files:
                    with patch("api.services.ideas_service.get_template_renderer") as mock_renderer:
                        with patch("api.services.ideas_service.get_research_service") as mock_research:
                            with patch("api.services.ideas_service.get_settings") as mock_settings:
                                mock_settings.return_value.use_langgraph_v2 = False
                                mock_settings.return_value.scoring = MagicMock(criteria=[])

                                from api.services.ideas_service import IdeasService

                                service = IdeasService()
                                service.ai = MagicMock()
                                service.prompts = MagicMock()
                                service.files = MagicMock()
                                service.renderer = MagicMock()
                                service.research = MagicMock()
                                service.config = mock_settings.return_value

                                return service

    @pytest.mark.asyncio
    async def test_generate_batch_success(self, service):
        """Test generating a batch of ideas."""
        service.ai.generate_json = AsyncMock(return_value={
            "ideas": [
                {
                    "title": "Idea One",
                    "concept": "Concept description",
                    "insight": "Consumer insight",
                    "formats": ["digital", "social"],
                },
                {
                    "title": "Idea Two",
                    "concept": "Another concept",
                    "insight": "Another insight",
                    "formats": ["video"],
                },
            ]
        })
        service.prompts.format.return_value = ("system", "user")

        concepts = await service._generate_batch(
            research_content="Research text",
            quick_reference="Quick ref",
            brief="Brief content",
            num_ideas=2,
            existing_ideas=[],
            creative_directions=None,
        )

        assert len(concepts) == 2
        assert concepts[0].title == "Idea One"
        assert concepts[1].title == "Idea Two"

    @pytest.mark.asyncio
    async def test_generate_batch_filters_similar(self, service):
        """Test batch generation filters similar ideas."""
        service.ai.generate_json = AsyncMock(return_value={
            "ideas": [
                {"title": "Banking Innovation", "concept": "Digital banking"},
            ]
        })
        service.prompts.format.return_value = ("system", "user")

        # Existing idea with similar title
        concepts = await service._generate_batch(
            research_content="",
            quick_reference="",
            brief="",
            num_ideas=1,
            existing_ideas=["Banking Innovation Campaign"],  # Similar
            creative_directions=None,
        )

        # Should filter out similar idea
        assert len(concepts) <= 1


class TestIdeaExpansion:
    """Tests for idea expansion."""

    @pytest.fixture
    def service(self):
        """Create ideas service with mocked dependencies."""
        with patch("api.services.ideas_service.get_ai_manager"):
            with patch("api.services.ideas_service.get_prompt_loader"):
                with patch("api.services.ideas_service.get_file_service"):
                    with patch("api.services.ideas_service.get_template_renderer"):
                        with patch("api.services.ideas_service.get_research_service"):
                            with patch("api.services.ideas_service.get_settings") as mock_settings:
                                mock_settings.return_value.scoring = MagicMock(criteria=[])

                                from api.services.ideas_service import IdeasService

                                service = IdeasService()
                                service.ai = MagicMock()
                                service.prompts = MagicMock()
                                service.config = mock_settings.return_value

                                return service

    @pytest.mark.asyncio
    async def test_expand_single_idea(self, service):
        """Test expanding a single idea."""
        from api.models import IdeaConcept

        service.ai.generate_json = AsyncMock(return_value={
            "concept": "Expanded concept",
            "insight": "Deep insight",
            "execution": {"headline": "Big Headline"},
            "scores": {
                "diferenciacion": 8,
                "relevancia_cultural": 9,
                "claridad_insight": 7,
                "ejecutabilidad": 8,
                "potencial_viral": 7,
                "memorabilidad": 8,
                "versatilidad": 7,
                "alineacion_marca": 9,
                "potencial_pr": 6,
                "escalabilidad": 8,
            },
            "strengths": ["Strong brand fit"],
            "weaknesses": ["Budget required"],
            "recommendation": "Proceed with pilot",
        })
        service.prompts.format.return_value = ("system", "user")

        concept = IdeaConcept(
            number=1,
            title="Test Idea",
            concept="Initial concept",
            insight="Initial insight",
            formats=["digital"],
        )

        expanded = await service._expand_single_idea(
            concept=concept,
            brief="Brief",
            quick_reference="Quick ref",
            country="Paraguay",
        )

        assert expanded.concept == "Expanded concept"
        assert expanded.scores.diferenciacion == 8
        assert "Strong brand fit" in expanded.strengths


class TestValidation:
    """Tests for idea validation."""

    @pytest.fixture
    def service(self):
        """Create ideas service with mocked dependencies."""
        with patch("api.services.ideas_service.get_ai_manager"):
            with patch("api.services.ideas_service.get_prompt_loader"):
                with patch("api.services.ideas_service.get_file_service"):
                    with patch("api.services.ideas_service.get_template_renderer"):
                        with patch("api.services.ideas_service.get_research_service"):
                            with patch("api.services.ideas_service.get_settings") as mock_settings:
                                mock_settings.return_value.scoring = MagicMock(criteria=[])

                                from api.services.ideas_service import IdeasService

                                service = IdeasService()
                                service.ai = MagicMock()
                                service.prompts = MagicMock()

                                return service

    @pytest.mark.asyncio
    async def test_validate_quality(self, service):
        """Test quality validation."""
        from api.models import IdeaExpanded, IdeaScores

        service.ai.generate_json = AsyncMock(return_value={
            "scores": {"clarity": 8, "feasibility": 9},
            "overall": 8.5,
            "strengths": ["Clear message"],
            "weaknesses": ["Budget intensive"],
            "suggestions": ["Consider phased rollout"],
        })
        service.prompts.format.return_value = ("system", "user")

        idea = IdeaExpanded(
            number=1,
            title="Test",
            concept="Test concept",
            insight="Test insight",
            execution={},
            scores=IdeaScores(),
            overall_score=0,
            tier="",
            strengths=[],
            weaknesses=[],
            recommendation="",
        )

        validation = await service._validate_quality(idea)

        assert validation.overall == 8.5
        assert "Clear message" in validation.strengths

    @pytest.mark.asyncio
    async def test_validate_cultural(self, service):
        """Test cultural validation."""
        from api.models import IdeaExpanded, IdeaScores

        service.ai.generate_json = AsyncMock(return_value={
            "cultural_score": 9,
            "positives": ["Respects local traditions"],
            "concerns": [],
            "suggestions": [],
            "approved": True,
        })
        service.prompts.format.return_value = ("system", "user")

        idea = IdeaExpanded(
            number=1,
            title="Test",
            concept="Test concept",
            insight="Test insight",
            execution={},
            scores=IdeaScores(),
            overall_score=0,
            tier="",
            strengths=[],
            weaknesses=[],
            recommendation="",
        )

        validation = await service._validate_cultural(idea, "Paraguay")

        assert validation.cultural_score == 9
        assert validation.approved is True


class TestScoring:
    """Tests for idea scoring."""

    @pytest.fixture
    def service(self):
        """Create ideas service with scoring config."""
        with patch("api.services.ideas_service.get_ai_manager"):
            with patch("api.services.ideas_service.get_prompt_loader"):
                with patch("api.services.ideas_service.get_file_service"):
                    with patch("api.services.ideas_service.get_template_renderer"):
                        with patch("api.services.ideas_service.get_research_service"):
                            with patch("api.services.ideas_service.get_settings") as mock_settings:
                                from api.config import ScoringCriterion

                                mock_settings.return_value.scoring = MagicMock(
                                    criteria=[
                                        ScoringCriterion(name="diferenciacion", weight=1.5),
                                        ScoringCriterion(name="relevancia_cultural", weight=1.5),
                                        ScoringCriterion(name="claridad_insight", weight=1.0),
                                        ScoringCriterion(name="ejecutabilidad", weight=1.2),
                                    ]
                                )

                                from api.services.ideas_service import IdeasService

                                service = IdeasService()
                                service.config = mock_settings.return_value

                                return service

    def test_calculate_weighted_score(self, service):
        """Test weighted score calculation."""
        scores = {
            "diferenciacion": 8,
            "relevancia_cultural": 9,
            "claridad_insight": 7,
            "ejecutabilidad": 8,
        }

        result = service._calculate_weighted_score(scores)

        # Expected: (8*1.5 + 9*1.5 + 7*1.0 + 8*1.2) / (1.5+1.5+1.0+1.2)
        # = (12 + 13.5 + 7 + 9.6) / 5.2 = 42.1 / 5.2 ≈ 8.1
        assert 8.0 <= result <= 8.2

    def test_calculate_weighted_score_empty(self, service):
        """Test weighted score with empty scores."""
        result = service._calculate_weighted_score({})

        assert result == 0


class TestTierClassification:
    """Tests for tier classification."""

    @pytest.fixture
    def service(self):
        """Create ideas service."""
        with patch("api.services.ideas_service.get_ai_manager"):
            with patch("api.services.ideas_service.get_prompt_loader"):
                with patch("api.services.ideas_service.get_file_service"):
                    with patch("api.services.ideas_service.get_template_renderer"):
                        with patch("api.services.ideas_service.get_research_service"):
                            with patch("api.services.ideas_service.get_settings") as mock_settings:
                                mock_settings.return_value.scoring = MagicMock(criteria=[])

                                from api.services.ideas_service import IdeasService

                                return IdeasService()

    def test_tier_exceptional(self, service):
        """Test Tier 1 classification."""
        tier = service._get_tier(9.5)
        assert "Tier 1" in tier
        assert "Excepcional" in tier

    def test_tier_solid(self, service):
        """Test Tier 2 classification."""
        tier = service._get_tier(8.5)
        assert "Tier 2" in tier
        assert "Sólida" in tier

    def test_tier_promising(self, service):
        """Test Tier 3 classification."""
        tier = service._get_tier(7.5)
        assert "Tier 3" in tier
        assert "Promisoria" in tier

    def test_tier_needs_work(self, service):
        """Test Tier 4 classification."""
        tier = service._get_tier(6.5)
        assert "Tier 4" in tier
        assert "Necesita Trabajo" in tier

    def test_tier_reconsider(self, service):
        """Test Tier 5 classification."""
        tier = service._get_tier(5.0)
        assert "Tier 5" in tier
        assert "Reconsiderar" in tier


class TestMarkdownExtraction:
    """Tests for markdown content extraction."""

    @pytest.fixture
    def service(self):
        """Create ideas service."""
        with patch("api.services.ideas_service.get_ai_manager"):
            with patch("api.services.ideas_service.get_prompt_loader"):
                with patch("api.services.ideas_service.get_file_service"):
                    with patch("api.services.ideas_service.get_template_renderer"):
                        with patch("api.services.ideas_service.get_research_service"):
                            with patch("api.services.ideas_service.get_settings") as mock_settings:
                                mock_settings.return_value.scoring = MagicMock(criteria=[])

                                from api.services.ideas_service import IdeasService

                                return IdeasService()

    def test_extract_score_from_markdown(self, service):
        """Test score extraction from markdown."""
        content = """
# Idea Title

## Scores
- Diferenciación: 8
- Promedio Ponderado: 8.5

## Summary
"""
        score = service._extract_score_from_markdown(content)

        assert score == 8.5

    def test_extract_score_overall(self, service):
        """Test Overall score extraction."""
        content = "Overall Score: 7.8"

        score = service._extract_score_from_markdown(content)

        assert score == 7.8

    def test_extract_score_default(self, service):
        """Test default score when not found."""
        content = "No score here"

        score = service._extract_score_from_markdown(content)

        assert score == 5.0

    def test_extract_title_from_markdown(self, service):
        """Test title extraction from markdown."""
        content = """# Campaign Idea Title

## Concept
Description here.
"""
        title = service._extract_title_from_markdown(content)

        assert title == "Campaign Idea Title"

    def test_extract_title_default(self, service):
        """Test default title when not found."""
        content = "No heading here"

        title = service._extract_title_from_markdown(content)

        assert title == "Untitled"


class TestRecommendations:
    """Tests for recommendation generation."""

    @pytest.fixture
    def service(self):
        """Create ideas service."""
        with patch("api.services.ideas_service.get_ai_manager"):
            with patch("api.services.ideas_service.get_prompt_loader"):
                with patch("api.services.ideas_service.get_file_service"):
                    with patch("api.services.ideas_service.get_template_renderer"):
                        with patch("api.services.ideas_service.get_research_service"):
                            with patch("api.services.ideas_service.get_settings") as mock_settings:
                                mock_settings.return_value.scoring = MagicMock(criteria=[])

                                from api.services.ideas_service import IdeasService

                                return IdeasService()

    def test_recommendations_exceptional_idea(self, service):
        """Test recommendations for exceptional top idea."""
        from api.models import IdeaSummary

        ideas = [
            IdeaSummary(number=1, title="Best Idea", overall_score=9.0, tier="Tier 1 - Excepcional"),
            IdeaSummary(number=2, title="Good Idea", overall_score=8.0, tier="Tier 2 - Sólida"),
        ]

        recommendations = service._generate_recommendations(ideas)

        assert any("prioridad principal" in r.lower() for r in recommendations)

    def test_recommendations_low_average(self, service):
        """Test recommendations for low average score."""
        from api.models import IdeaSummary

        ideas = [
            IdeaSummary(number=1, title="Okay Idea", overall_score=6.5, tier="Tier 4"),
            IdeaSummary(number=2, title="Weak Idea", overall_score=6.0, tier="Tier 4"),
        ]

        recommendations = service._generate_recommendations(ideas)

        assert any("promedio general es bajo" in r.lower() for r in recommendations)

    def test_recommendations_multiple_tier1(self, service):
        """Test recommendations with multiple Tier 1 ideas."""
        from api.models import IdeaSummary

        ideas = [
            IdeaSummary(number=1, title="Idea 1", overall_score=9.5, tier="Tier 1 - Excepcional"),
            IdeaSummary(number=2, title="Idea 2", overall_score=9.2, tier="Tier 1 - Excepcional"),
            IdeaSummary(number=3, title="Idea 3", overall_score=9.0, tier="Tier 1 - Excepcional"),
        ]

        recommendations = service._generate_recommendations(ideas)

        assert any("3 ideas excepcionales" in r.lower() for r in recommendations)

    def test_recommendations_no_tier1(self, service):
        """Test recommendations when no Tier 1 ideas."""
        from api.models import IdeaSummary

        ideas = [
            IdeaSummary(number=1, title="Good Idea", overall_score=8.5, tier="Tier 2 - Sólida"),
            IdeaSummary(number=2, title="Another", overall_score=8.0, tier="Tier 2 - Sólida"),
        ]

        recommendations = service._generate_recommendations(ideas)

        assert any("no hay ideas tier 1" in r.lower() for r in recommendations)

    def test_recommendations_empty_list(self, service):
        """Test recommendations with empty idea list."""
        recommendations = service._generate_recommendations([])

        assert any("no hay ideas" in r.lower() for r in recommendations)


class TestIdeasServiceSingleton:
    """Tests for singleton access."""

    def test_get_ideas_service_returns_same_instance(self):
        """Test singleton pattern."""
        with patch("api.services.ideas_service.get_ai_manager"):
            with patch("api.services.ideas_service.get_prompt_loader"):
                with patch("api.services.ideas_service.get_file_service"):
                    with patch("api.services.ideas_service.get_template_renderer"):
                        with patch("api.services.ideas_service.get_research_service"):
                            with patch("api.services.ideas_service.get_settings") as mock_settings:
                                mock_settings.return_value.scoring = MagicMock(criteria=[])

                                # Reset singleton
                                import api.services.ideas_service
                                api.services.ideas_service._ideas_service = None

                                from api.services.ideas_service import get_ideas_service

                                service1 = get_ideas_service()
                                service2 = get_ideas_service()

                                assert service1 is service2
