"""
API tests for ideas routes.

Tests cover:
- Idea generation
- Idea expansion
- Idea scoring
- Idea listing
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class TestIdeasGenerationRoutes:
    """Tests for idea generation endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.ideas.get_ideas_service") as mock_is:
            mock_ideas_service = MagicMock()
            mock_is.return_value = mock_ideas_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_ideas_service

    @pytest.fixture
    def sample_idea_response(self):
        """Sample idea generation response."""
        return {
            "project_id": "test-project",
            "ideas_generated": 5,
            "concepts": [
                {
                    "number": 1,
                    "title": "Idea One",
                    "concept": "Description",
                    "insight": "Consumer insight",
                    "formats": ["digital"],
                },
            ],
            "files_created": ["idea-001.md"],
        }

    @pytest.mark.asyncio
    async def test_generate_ideas(self, client, sample_idea_response):
        """Test generating ideas."""
        test_client, mock_is = client
        mock_is.generate_ideas = AsyncMock(return_value=MagicMock(
            **sample_idea_response,
            model_dump=MagicMock(return_value=sample_idea_response),
        ))

        response = await test_client.post(
            "/projects/test-project/ideas/generate",
            json={
                "num_ideas": 5,
                "batch_size": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ideas_generated"] == 5

    @pytest.mark.asyncio
    async def test_generate_ideas_with_directions(self, client, sample_idea_response):
        """Test generating ideas with creative directions."""
        test_client, mock_is = client
        mock_is.generate_ideas = AsyncMock(return_value=MagicMock(
            **sample_idea_response,
            model_dump=MagicMock(return_value=sample_idea_response),
        ))

        response = await test_client.post(
            "/projects/test-project/ideas/generate",
            json={
                "num_ideas": 5,
                "creative_directions": ["humor", "emotional"],
            },
        )

        assert response.status_code == 200
        mock_is.generate_ideas.assert_called_once()
        call_kwargs = mock_is.generate_ideas.call_args[1]
        assert call_kwargs.get("creative_directions") == ["humor", "emotional"]

    @pytest.mark.asyncio
    async def test_generate_ideas_default_params(self, client, sample_idea_response):
        """Test generating ideas with default parameters."""
        test_client, mock_is = client
        mock_is.generate_ideas = AsyncMock(return_value=MagicMock(
            **sample_idea_response,
            model_dump=MagicMock(return_value=sample_idea_response),
        ))

        response = await test_client.post(
            "/projects/test-project/ideas/generate",
            json={},  # No params, use defaults
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_generate_ideas_project_not_found(self, client):
        """Test generating ideas for non-existent project."""
        test_client, mock_is = client
        mock_is.generate_ideas = AsyncMock(side_effect=FileNotFoundError("Project not found"))

        response = await test_client.post(
            "/projects/nonexistent/ideas/generate",
            json={"num_ideas": 5},
        )

        assert response.status_code == 404


class TestIdeaExpansionRoutes:
    """Tests for idea expansion endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.ideas.get_ideas_service") as mock_is:
            mock_ideas_service = MagicMock()
            mock_is.return_value = mock_ideas_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_ideas_service

    @pytest.fixture
    def sample_expand_response(self):
        """Sample idea expansion response."""
        return {
            "project_id": "test-project",
            "idea": {
                "number": 1,
                "title": "Expanded Idea",
                "concept": "Full concept description",
                "insight": "Deep consumer insight",
                "execution": {"headline": "Big Bold Headline"},
                "scores": {
                    "diferenciacion": 8,
                    "relevancia_cultural": 9,
                },
                "overall_score": 8.5,
                "tier": "Tier 2 - Sólida",
                "strengths": ["Strong brand fit"],
                "weaknesses": ["Budget intensive"],
                "recommendation": "Proceed with pilot",
            },
            "file_path": "ideas/idea-001.md",
        }

    @pytest.mark.asyncio
    async def test_expand_idea(self, client, sample_expand_response):
        """Test expanding an idea."""
        test_client, mock_is = client
        mock_is.expand_idea = AsyncMock(return_value=MagicMock(
            **sample_expand_response,
            model_dump=MagicMock(return_value=sample_expand_response),
        ))

        response = await test_client.post(
            "/projects/test-project/ideas/1/expand",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["idea"]["overall_score"] == 8.5

    @pytest.mark.asyncio
    async def test_expand_idea_not_found(self, client):
        """Test expanding non-existent idea."""
        test_client, mock_is = client
        mock_is.expand_idea = AsyncMock(side_effect=FileNotFoundError("Idea not found"))

        response = await test_client.post(
            "/projects/test-project/ideas/999/expand",
        )

        assert response.status_code == 404


class TestIdeaScoringRoutes:
    """Tests for idea scoring endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.ideas.get_ideas_service") as mock_is:
            mock_ideas_service = MagicMock()
            mock_is.return_value = mock_ideas_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_ideas_service

    @pytest.fixture
    def sample_score_response(self):
        """Sample scoring response."""
        return {
            "project_id": "test-project",
            "total_ideas": 25,
            "tier_distribution": {
                "Tier 1": 3,
                "Tier 2": 8,
                "Tier 3": 10,
                "Tier 4": 4,
                "Tier 5": 0,
            },
            "top_ideas": [
                {"number": 5, "title": "Best Idea", "overall_score": 9.2, "tier": "Tier 1"},
                {"number": 12, "title": "Great Idea", "overall_score": 9.0, "tier": "Tier 1"},
            ],
            "summary_file": "ideas-summary.md",
        }

    @pytest.mark.asyncio
    async def test_score_all_ideas(self, client, sample_score_response):
        """Test scoring all ideas."""
        test_client, mock_is = client
        mock_is.score_all_ideas = AsyncMock(return_value=MagicMock(
            **sample_score_response,
            model_dump=MagicMock(return_value=sample_score_response),
        ))

        response = await test_client.post(
            "/projects/test-project/ideas/score",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_ideas"] == 25
        assert data["tier_distribution"]["Tier 1"] == 3

    @pytest.mark.asyncio
    async def test_score_all_ideas_recalculate(self, client, sample_score_response):
        """Test recalculating scores."""
        test_client, mock_is = client
        mock_is.score_all_ideas = AsyncMock(return_value=MagicMock(
            **sample_score_response,
            model_dump=MagicMock(return_value=sample_score_response),
        ))

        response = await test_client.post(
            "/projects/test-project/ideas/score",
            json={"recalculate": True},
        )

        assert response.status_code == 200
        call_kwargs = mock_is.score_all_ideas.call_args[1]
        assert call_kwargs.get("recalculate") is True


class TestIdeasListRoutes:
    """Tests for ideas listing endpoints."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.ideas.get_file_service") as mock_fs:
            mock_file_service = MagicMock()
            mock_fs.return_value = mock_file_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_file_service

    @pytest.mark.asyncio
    async def test_list_ideas(self, client):
        """Test listing ideas."""
        test_client, mock_fs = client
        mock_fs.get_idea_files = MagicMock(return_value=[
            "ideas/idea-001.md",
            "ideas/idea-002.md",
            "ideas/idea-003.md",
        ])

        response = await test_client.get("/projects/test-project/ideas")

        assert response.status_code == 200
        data = response.json()
        assert len(data["ideas"]) == 3

    @pytest.mark.asyncio
    async def test_list_ideas_empty(self, client):
        """Test listing ideas when none exist."""
        test_client, mock_fs = client
        mock_fs.get_idea_files = MagicMock(return_value=[])

        response = await test_client.get("/projects/test-project/ideas")

        assert response.status_code == 200
        data = response.json()
        assert data["ideas"] == []

    @pytest.mark.asyncio
    async def test_get_idea(self, client):
        """Test getting a specific idea."""
        test_client, mock_fs = client
        mock_fs.read_file = AsyncMock(return_value="""# Idea Title

## Concept
Test concept description.

## Score
Overall Score: 8.5
""")

        response = await test_client.get("/projects/test-project/ideas/1")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_idea_not_found(self, client):
        """Test getting non-existent idea."""
        test_client, mock_fs = client
        mock_fs.read_file = AsyncMock(side_effect=FileNotFoundError())

        response = await test_client.get("/projects/test-project/ideas/999")

        assert response.status_code == 404


class TestIdeasAgentRoutes:
    """Tests for LangGraph agent-based idea generation."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.ideas.get_ideas_service") as mock_is:
            mock_ideas_service = MagicMock()
            mock_is.return_value = mock_ideas_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_ideas_service

    @pytest.mark.asyncio
    async def test_generate_ideas_agent(self, client):
        """Test agent-based idea generation."""
        test_client, mock_is = client
        mock_is.generate_ideas = AsyncMock(return_value=MagicMock(
            project_id="test-project",
            ideas_generated=5,
            concepts=[],
            files_created=[],
            model_dump=MagicMock(return_value={
                "project_id": "test-project",
                "ideas_generated": 5,
                "concepts": [],
                "files_created": [],
            }),
        ))

        response = await test_client.post(
            "/projects/test-project/ideas/agent",
            json={"num_ideas": 5},
        )

        assert response.status_code == 200


class TestIdeasRoutesErrorHandling:
    """Tests for error handling in ideas routes."""

    @pytest_asyncio.fixture
    async def client(self):
        """Create test client with mocked dependencies."""
        with patch("api.routes.ideas.get_ideas_service") as mock_is:
            mock_ideas_service = MagicMock()
            mock_is.return_value = mock_ideas_service

            from api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                yield client, mock_ideas_service

    @pytest.mark.asyncio
    async def test_generate_ideas_server_error(self, client):
        """Test server error during idea generation."""
        test_client, mock_is = client
        mock_is.generate_ideas = AsyncMock(side_effect=Exception("AI provider error"))

        response = await test_client.post(
            "/projects/test-project/ideas/generate",
            json={"num_ideas": 5},
        )

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_score_ideas_server_error(self, client):
        """Test server error during scoring."""
        test_client, mock_is = client
        mock_is.score_all_ideas = AsyncMock(side_effect=Exception("Scoring failed"))

        response = await test_client.post(
            "/projects/test-project/ideas/score",
        )

        assert response.status_code == 500
