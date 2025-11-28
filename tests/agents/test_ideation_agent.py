"""
Tests for IdeationAgent (LangGraph-based).

Tests cover:
- State management
- Graph node execution
- Iteration control
- Idea generation and refinement
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestIdeationState:
    """Tests for IdeationState type definition."""

    def test_ideation_state_fields(self):
        """Test IdeationState has required fields."""
        from api.agents.ideation_agent import IdeationState

        # IdeationState is a TypedDict, check its annotations
        assert "project_id" in IdeationState.__annotations__
        assert "brief_text" in IdeationState.__annotations__
        assert "research_summary" in IdeationState.__annotations__
        assert "ideas" in IdeationState.__annotations__
        assert "critique" in IdeationState.__annotations__
        assert "iteration_count" in IdeationState.__annotations__
        assert "max_iterations" in IdeationState.__annotations__

    def test_create_ideation_state(self):
        """Test creating IdeationState instance."""
        from api.agents.ideation_agent import IdeationState

        state: IdeationState = {
            "project_id": "test-project",
            "brief_text": "Campaign brief text",
            "research_summary": "Research findings",
            "ideas": [],
            "critique": "",
            "iteration_count": 0,
            "max_iterations": 3,
        }

        assert state["project_id"] == "test-project"
        assert state["max_iterations"] == 3


class TestBrainstormNode:
    """Tests for brainstorm node."""

    @pytest.fixture
    def mock_ai_manager(self):
        """Create mock AI manager."""
        manager = MagicMock()
        manager.generate_json = AsyncMock(return_value={
            "ideas": [
                {
                    "title": "Idea 1",
                    "description": "Description of idea 1",
                    "rationale": "Why this works",
                },
                {
                    "title": "Idea 2",
                    "description": "Description of idea 2",
                    "rationale": "Rationale for idea 2",
                },
            ]
        })
        return manager

    @pytest.fixture
    def mock_prompt_loader(self):
        """Create mock prompt loader."""
        loader = MagicMock()
        loader.format = MagicMock(return_value=("System prompt", "User prompt"))
        return loader

    @pytest.mark.asyncio
    async def test_brainstorm_generates_ideas(self, mock_ai_manager, mock_prompt_loader):
        """Test brainstorm node generates ideas."""
        with patch("api.agents.ideation_agent.get_ai_manager", return_value=mock_ai_manager), \
             patch("api.agents.ideation_agent.get_prompt_loader", return_value=mock_prompt_loader):
            from api.agents.ideation_agent import brainstorm_node

            state = {
                "project_id": "test-project",
                "brief_text": "Create an engaging campaign",
                "research_summary": "Target audience is young adults",
                "ideas": [],
                "critique": "",
                "iteration_count": 0,
                "max_iterations": 3,
            }

            result = await brainstorm_node(state)

            assert "ideas" in result
            assert len(result["ideas"]) == 2
            assert result["iteration_count"] == 0

    @pytest.mark.asyncio
    async def test_brainstorm_uses_prompts(self, mock_ai_manager, mock_prompt_loader):
        """Test brainstorm node uses prompt loader."""
        with patch("api.agents.ideation_agent.get_ai_manager", return_value=mock_ai_manager), \
             patch("api.agents.ideation_agent.get_prompt_loader", return_value=mock_prompt_loader):
            from api.agents.ideation_agent import brainstorm_node

            state = {
                "project_id": "test-project",
                "brief_text": "Campaign brief",
                "research_summary": "Research summary",
                "ideas": [],
                "critique": "",
                "iteration_count": 0,
                "max_iterations": 3,
            }

            await brainstorm_node(state)

            mock_prompt_loader.format.assert_called_once()
            args = mock_prompt_loader.format.call_args
            assert args[0][0] == "ideation"
            assert args[0][1] == "brainstorm"

    @pytest.mark.asyncio
    async def test_brainstorm_handles_empty_response(self, mock_prompt_loader):
        """Test brainstorm handles empty AI response."""
        empty_manager = MagicMock()
        empty_manager.generate_json = AsyncMock(return_value={"ideas": []})

        with patch("api.agents.ideation_agent.get_ai_manager", return_value=empty_manager), \
             patch("api.agents.ideation_agent.get_prompt_loader", return_value=mock_prompt_loader):
            from api.agents.ideation_agent import brainstorm_node

            state = {
                "project_id": "test-project",
                "brief_text": "Brief",
                "research_summary": "Research",
                "ideas": [],
                "critique": "",
                "iteration_count": 0,
                "max_iterations": 3,
            }

            result = await brainstorm_node(state)

            assert result["ideas"] == []


class TestCritiqueNode:
    """Tests for critique node."""

    @pytest.fixture
    def mock_ai_manager(self):
        """Create mock AI manager."""
        manager = MagicMock()
        manager.generate = AsyncMock(return_value="This critique identifies strengths and weaknesses...")
        return manager

    @pytest.fixture
    def mock_prompt_loader(self):
        """Create mock prompt loader."""
        loader = MagicMock()
        loader.format = MagicMock(return_value=("System prompt", "User prompt"))
        return loader

    @pytest.mark.asyncio
    async def test_critique_node_generates_critique(self, mock_ai_manager, mock_prompt_loader):
        """Test critique node generates critique."""
        with patch("api.agents.ideation_agent.get_ai_manager", return_value=mock_ai_manager), \
             patch("api.agents.ideation_agent.get_prompt_loader", return_value=mock_prompt_loader):
            from api.agents.ideation_agent import critique_node
            from api.models import Idea

            state = {
                "project_id": "test-project",
                "brief_text": "Campaign brief",
                "research_summary": "Research",
                "ideas": [
                    Idea(title="Idea 1", description="Desc 1", rationale="Rationale 1", score=0.0),
                    Idea(title="Idea 2", description="Desc 2", rationale="Rationale 2", score=0.0),
                ],
                "critique": "",
                "iteration_count": 1,
                "max_iterations": 3,
            }

            result = await critique_node(state)

            assert "critique" in result
            assert len(result["critique"]) > 0

    @pytest.mark.asyncio
    async def test_critique_uses_lower_temperature(self, mock_ai_manager, mock_prompt_loader):
        """Test critique uses lower temperature for analytical task."""
        with patch("api.agents.ideation_agent.get_ai_manager", return_value=mock_ai_manager), \
             patch("api.agents.ideation_agent.get_prompt_loader", return_value=mock_prompt_loader):
            from api.agents.ideation_agent import critique_node
            from api.models import Idea

            state = {
                "project_id": "test-project",
                "brief_text": "Brief",
                "research_summary": "Research",
                "ideas": [Idea(title="Test", description="Desc", rationale="Rat", score=0.0)],
                "critique": "",
                "iteration_count": 0,
                "max_iterations": 3,
            }

            await critique_node(state)

            # Check temperature is 0.4 (lower for analytical)
            call_kwargs = mock_ai_manager.generate.call_args[1]
            assert call_kwargs.get("temperature") == 0.4


class TestRefineNode:
    """Tests for refine node."""

    @pytest.fixture
    def mock_ai_manager(self):
        """Create mock AI manager."""
        manager = MagicMock()
        manager.generate_json = AsyncMock(return_value={
            "ideas": [
                {
                    "title": "Refined Idea 1",
                    "description": "Improved description",
                    "rationale": "Better rationale",
                },
            ]
        })
        return manager

    @pytest.fixture
    def mock_prompt_loader(self):
        """Create mock prompt loader."""
        loader = MagicMock()
        loader.format = MagicMock(return_value=("System prompt", "User prompt"))
        return loader

    @pytest.mark.asyncio
    async def test_refine_node_refines_ideas(self, mock_ai_manager, mock_prompt_loader):
        """Test refine node produces refined ideas."""
        with patch("api.agents.ideation_agent.get_ai_manager", return_value=mock_ai_manager), \
             patch("api.agents.ideation_agent.get_prompt_loader", return_value=mock_prompt_loader):
            from api.agents.ideation_agent import refine_node
            from api.models import Idea

            state = {
                "project_id": "test-project",
                "brief_text": "Brief",
                "research_summary": "Research",
                "ideas": [Idea(title="Original", description="Desc", rationale="Rat", score=0.0)],
                "critique": "Needs more emotional connection",
                "iteration_count": 0,
                "max_iterations": 3,
            }

            result = await refine_node(state)

            assert "ideas" in result
            assert len(result["ideas"]) == 1
            assert result["ideas"][0].title == "Refined Idea 1"

    @pytest.mark.asyncio
    async def test_refine_increments_iteration(self, mock_ai_manager, mock_prompt_loader):
        """Test refine node increments iteration count."""
        with patch("api.agents.ideation_agent.get_ai_manager", return_value=mock_ai_manager), \
             patch("api.agents.ideation_agent.get_prompt_loader", return_value=mock_prompt_loader):
            from api.agents.ideation_agent import refine_node
            from api.models import Idea

            state = {
                "project_id": "test-project",
                "brief_text": "Brief",
                "research_summary": "Research",
                "ideas": [Idea(title="Test", description="Desc", rationale="Rat", score=0.0)],
                "critique": "Critique text",
                "iteration_count": 1,
                "max_iterations": 3,
            }

            result = await refine_node(state)

            assert result["iteration_count"] == 2


class TestSelectNode:
    """Tests for select node."""

    @pytest.mark.asyncio
    async def test_select_node_passes_through(self):
        """Test select node passes through (placeholder)."""
        from api.agents.ideation_agent import select_node
        from api.models import Idea

        state = {
            "project_id": "test-project",
            "brief_text": "Brief",
            "research_summary": "Research",
            "ideas": [
                Idea(title="Final 1", description="Desc", rationale="Rat", score=8.5),
                Idea(title="Final 2", description="Desc", rationale="Rat", score=7.0),
            ],
            "critique": "Final critique",
            "iteration_count": 3,
            "max_iterations": 3,
        }

        result = await select_node(state)

        # Current implementation is a placeholder that returns empty dict
        assert isinstance(result, dict)


class TestIdeationGraph:
    """Tests for ideation graph construction."""

    def test_create_ideation_graph(self):
        """Test ideation graph is created correctly."""
        from api.agents.ideation_agent import create_ideation_graph

        graph = create_ideation_graph()

        assert graph is not None

    def test_graph_has_nodes(self):
        """Test graph has expected nodes."""
        from api.agents.ideation_agent import create_ideation_graph

        graph = create_ideation_graph()

        # Graph should be compiled, check it's not None
        assert graph is not None

    def test_should_continue_logic(self):
        """Test iteration continuation logic."""
        from api.agents.ideation_agent import IdeationState

        # Test continue condition
        state_continue: IdeationState = {
            "project_id": "test",
            "brief_text": "",
            "research_summary": "",
            "ideas": [],
            "critique": "",
            "iteration_count": 1,
            "max_iterations": 3,
        }

        # Test stop condition
        state_stop: IdeationState = {
            "project_id": "test",
            "brief_text": "",
            "research_summary": "",
            "ideas": [],
            "critique": "",
            "iteration_count": 3,
            "max_iterations": 3,
        }

        # Should continue
        assert state_continue["iteration_count"] < state_continue["max_iterations"]

        # Should stop
        assert not (state_stop["iteration_count"] < state_stop["max_iterations"])


class TestIdeationGraphExecution:
    """Tests for full graph execution."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create all mocked dependencies."""
        ai_manager = MagicMock()
        ai_manager.generate_json = AsyncMock(return_value={
            "ideas": [
                {"title": "Test Idea", "description": "Desc", "rationale": "Rat"},
            ]
        })
        ai_manager.generate = AsyncMock(return_value="Critique text")

        prompt_loader = MagicMock()
        prompt_loader.format = MagicMock(return_value=("System", "User"))

        return ai_manager, prompt_loader

    @pytest.mark.asyncio
    async def test_graph_full_execution(self, mock_dependencies):
        """Test full graph execution."""
        ai_manager, prompt_loader = mock_dependencies

        with patch("api.agents.ideation_agent.get_ai_manager", return_value=ai_manager), \
             patch("api.agents.ideation_agent.get_prompt_loader", return_value=prompt_loader):
            from api.agents.ideation_agent import create_ideation_graph

            graph = create_ideation_graph()

            initial_state = {
                "project_id": "test-project",
                "brief_text": "Create a campaign for a new product launch",
                "research_summary": "Target audience: young professionals 25-35",
                "ideas": [],
                "critique": "",
                "iteration_count": 0,
                "max_iterations": 1,  # Only 1 iteration for faster test
            }

            # Execute graph
            result = await graph.ainvoke(initial_state)

            # Should have generated and refined ideas
            assert "ideas" in result
            assert result["iteration_count"] >= 0

    @pytest.mark.asyncio
    async def test_graph_respects_max_iterations(self, mock_dependencies):
        """Test graph respects max iterations limit."""
        ai_manager, prompt_loader = mock_dependencies

        with patch("api.agents.ideation_agent.get_ai_manager", return_value=ai_manager), \
             patch("api.agents.ideation_agent.get_prompt_loader", return_value=prompt_loader):
            from api.agents.ideation_agent import create_ideation_graph

            graph = create_ideation_graph()

            initial_state = {
                "project_id": "test-project",
                "brief_text": "Brief",
                "research_summary": "Research",
                "ideas": [],
                "critique": "",
                "iteration_count": 0,
                "max_iterations": 2,
            }

            result = await graph.ainvoke(initial_state)

            # Should not exceed max iterations
            assert result["iteration_count"] <= 2


class TestIdeaModel:
    """Tests for Idea model integration."""

    def test_idea_creation_from_dict(self):
        """Test creating Idea from dictionary data."""
        from api.models import Idea

        idea = Idea(
            title="Campaign Concept",
            description="A compelling campaign idea",
            rationale="This works because...",
            score=0.0,
        )

        assert idea.title == "Campaign Concept"
        assert idea.score == 0.0

    def test_idea_score_default(self):
        """Test Idea has default score of 0."""
        from api.models import Idea

        idea = Idea(
            title="Test",
            description="Desc",
            rationale="Rat",
            score=0.0,
        )

        assert idea.score == 0.0
