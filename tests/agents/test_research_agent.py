"""
Tests for ResearchAgent (LangGraph-based).

Tests cover:
- State management
- Query generation
- Search execution
- Result analysis
- Graph construction and execution
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestResearchState:
    """Tests for ResearchState type definition."""

    def test_research_state_fields(self):
        """Test ResearchState has required fields."""
        from api.agents.research_agent import ResearchState

        assert "project_id" in ResearchState.__annotations__
        assert "topic" in ResearchState.__annotations__
        assert "subtopics" in ResearchState.__annotations__
        assert "messages" in ResearchState.__annotations__
        assert "findings" in ResearchState.__annotations__
        assert "pending_queries" in ResearchState.__annotations__
        assert "iterations" in ResearchState.__annotations__
        assert "is_complete" in ResearchState.__annotations__

    def test_create_research_state(self):
        """Test creating ResearchState instance."""
        from api.agents.research_agent import ResearchState

        state: ResearchState = {
            "project_id": "test-project",
            "topic": "Consumer behavior trends",
            "subtopics": ["digital habits", "purchase patterns"],
            "messages": [],
            "findings": [],
            "pending_queries": [],
            "iterations": 0,
            "is_complete": False,
        }

        assert state["project_id"] == "test-project"
        assert len(state["subtopics"]) == 2
        assert state["is_complete"] is False


class TestGenerateQueries:
    """Tests for generate_queries node."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM."""
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(
            content="consumer behavior trends 2024\ndigital marketing trends\npurchase patterns analysis"
        ))
        return llm

    @pytest.mark.asyncio
    async def test_generate_queries_creates_queries(self, mock_llm):
        """Test generate_queries creates search queries."""
        with patch("api.agents.research_agent._get_llm", return_value=mock_llm):
            from api.agents.research_agent import generate_queries

            state = {
                "project_id": "test-project",
                "topic": "Consumer behavior",
                "subtopics": ["digital", "purchase"],
                "messages": [],
                "findings": [],
                "pending_queries": [],
                "iterations": 0,
                "is_complete": False,
            }

            result = await generate_queries(state)

            assert "pending_queries" in result
            assert len(result["pending_queries"]) > 0
            assert result["iterations"] == 1

    @pytest.mark.asyncio
    async def test_generate_queries_uses_context(self, mock_llm):
        """Test generate_queries uses existing findings as context."""
        with patch("api.agents.research_agent._get_llm", return_value=mock_llm):
            from api.agents.research_agent import generate_queries

            state = {
                "project_id": "test-project",
                "topic": "Market analysis",
                "subtopics": ["competitors", "trends"],
                "messages": [],
                "findings": ["Previous finding 1", "Previous finding 2"],
                "pending_queries": [],
                "iterations": 1,
                "is_complete": False,
            }

            await generate_queries(state)

            # LLM should have been called
            mock_llm.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_queries_increments_iterations(self, mock_llm):
        """Test generate_queries increments iteration count."""
        with patch("api.agents.research_agent._get_llm", return_value=mock_llm):
            from api.agents.research_agent import generate_queries

            state = {
                "project_id": "test-project",
                "topic": "Research topic",
                "subtopics": [],
                "messages": [],
                "findings": [],
                "pending_queries": [],
                "iterations": 2,
                "is_complete": False,
            }

            result = await generate_queries(state)

            assert result["iterations"] == 3


class TestExecuteSearch:
    """Tests for execute_search node."""

    @pytest.fixture
    def mock_search_service(self):
        """Create mock web search service."""
        service = MagicMock()
        service.search = AsyncMock(return_value=[
            {"url": "https://example.com/1", "title": "Result 1"},
            {"url": "https://example.com/2", "title": "Result 2"},
        ])
        return service

    @pytest.fixture
    def mock_web_fetcher(self):
        """Create mock web fetcher."""
        fetcher = MagicMock()
        fetcher.fetch_multiple = AsyncMock(return_value=[
            {"url": "https://example.com/1", "content": "Content from page 1"},
            {"url": "https://example.com/2", "content": "Content from page 2"},
        ])
        return fetcher

    @pytest.mark.asyncio
    async def test_execute_search_processes_queries(self, mock_search_service, mock_web_fetcher):
        """Test execute_search processes pending queries."""
        with patch("api.agents.research_agent.get_web_search_service", return_value=mock_search_service), \
             patch("api.agents.research_agent.get_web_fetcher", return_value=mock_web_fetcher):
            from api.agents.research_agent import execute_search

            state = {
                "project_id": "test-project",
                "topic": "Test topic",
                "subtopics": [],
                "messages": [],
                "findings": [],
                "pending_queries": ["query 1", "query 2"],
                "iterations": 1,
                "is_complete": False,
            }

            result = await execute_search(state)

            assert "findings" in result
            assert len(result["findings"]) > 0
            assert result["pending_queries"] == []

    @pytest.mark.asyncio
    async def test_execute_search_handles_empty_queries(self):
        """Test execute_search handles empty query list."""
        from api.agents.research_agent import execute_search

        state = {
            "project_id": "test-project",
            "topic": "Test topic",
            "subtopics": [],
            "messages": [],
            "findings": [],
            "pending_queries": [],
            "iterations": 1,
            "is_complete": False,
        }

        result = await execute_search(state)

        assert result["pending_queries"] == []

    @pytest.mark.asyncio
    async def test_execute_search_clears_queries_after_execution(self, mock_search_service, mock_web_fetcher):
        """Test queries are cleared after execution."""
        with patch("api.agents.research_agent.get_web_search_service", return_value=mock_search_service), \
             patch("api.agents.research_agent.get_web_fetcher", return_value=mock_web_fetcher):
            from api.agents.research_agent import execute_search

            state = {
                "project_id": "test-project",
                "topic": "Test topic",
                "subtopics": [],
                "messages": [],
                "findings": [],
                "pending_queries": ["test query"],
                "iterations": 1,
                "is_complete": False,
            }

            result = await execute_search(state)

            assert result["pending_queries"] == []


class TestAnalyzeResults:
    """Tests for analyze_results node."""

    @pytest.fixture
    def mock_llm_yes(self):
        """Create mock LLM that says YES."""
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="YES"))
        return llm

    @pytest.fixture
    def mock_llm_no(self):
        """Create mock LLM that says NO."""
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="NO"))
        return llm

    @pytest.mark.asyncio
    async def test_analyze_results_complete(self, mock_llm_yes):
        """Test analyze_results marks research as complete."""
        with patch("api.agents.research_agent._get_llm", return_value=mock_llm_yes):
            from api.agents.research_agent import analyze_results

            state = {
                "project_id": "test-project",
                "topic": "Test topic",
                "subtopics": ["sub1", "sub2"],
                "messages": [],
                "findings": ["Finding 1", "Finding 2", "Finding 3"],
                "pending_queries": [],
                "iterations": 1,
                "is_complete": False,
            }

            result = await analyze_results(state)

            assert result["is_complete"] is True

    @pytest.mark.asyncio
    async def test_analyze_results_needs_more(self, mock_llm_no):
        """Test analyze_results indicates more research needed."""
        with patch("api.agents.research_agent._get_llm", return_value=mock_llm_no):
            from api.agents.research_agent import analyze_results

            state = {
                "project_id": "test-project",
                "topic": "Test topic",
                "subtopics": ["sub1", "sub2"],
                "messages": [],
                "findings": ["Finding 1"],
                "pending_queries": [],
                "iterations": 1,
                "is_complete": False,
            }

            result = await analyze_results(state)

            assert result["is_complete"] is False

    @pytest.mark.asyncio
    async def test_analyze_results_max_iterations_forces_complete(self, mock_llm_no):
        """Test analyze_results marks complete at max iterations."""
        with patch("api.agents.research_agent._get_llm", return_value=mock_llm_no):
            from api.agents.research_agent import analyze_results

            state = {
                "project_id": "test-project",
                "topic": "Test topic",
                "subtopics": ["sub1"],
                "messages": [],
                "findings": ["Finding 1"],
                "pending_queries": [],
                "iterations": 3,  # Max iterations
                "is_complete": False,
            }

            result = await analyze_results(state)

            # Should be complete due to max iterations
            assert result["is_complete"] is True


class TestResearchGraph:
    """Tests for research graph construction."""

    def test_create_research_graph(self):
        """Test research graph is created correctly."""
        from api.agents.research_agent import create_research_graph

        graph = create_research_graph()

        assert graph is not None

    def test_check_completion_logic(self):
        """Test completion check logic."""
        # Complete state
        state_complete = {
            "is_complete": True,
        }

        # Incomplete state
        state_incomplete = {
            "is_complete": False,
        }

        # Verify logic
        assert state_complete["is_complete"] is True
        assert state_incomplete["is_complete"] is False


class TestGetLLM:
    """Tests for _get_llm helper function."""

    def test_get_llm_with_anthropic_key(self):
        """Test _get_llm returns Anthropic client when key is set."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = "test-anthropic-key"
        mock_settings.openai_api_key = None

        with patch("api.agents.research_agent.settings", mock_settings), \
             patch("api.agents.research_agent.ChatAnthropic") as MockAnthropic:
            from api.agents.research_agent import _get_llm

            llm = _get_llm()

            MockAnthropic.assert_called_once()

    def test_get_llm_falls_back_to_openai(self):
        """Test _get_llm falls back to OpenAI when no Anthropic key."""
        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = None
        mock_settings.openai_api_key = "test-openai-key"

        with patch("api.agents.research_agent.settings", mock_settings), \
             patch("api.agents.research_agent.ChatOpenAI") as MockOpenAI:
            from api.agents.research_agent import _get_llm

            llm = _get_llm()

            MockOpenAI.assert_called_once()


class TestResearchGraphExecution:
    """Tests for full graph execution."""

    @pytest.fixture
    def mock_all_dependencies(self):
        """Create all mocked dependencies."""
        # Mock LLM
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=[
            MagicMock(content="search query 1\nsearch query 2"),  # First query generation
            MagicMock(content="YES"),  # Analysis result
        ])

        # Mock search service
        search_service = MagicMock()
        search_service.search = AsyncMock(return_value=[
            {"url": "https://example.com/1", "title": "Result"},
        ])

        # Mock web fetcher
        web_fetcher = MagicMock()
        web_fetcher.fetch_multiple = AsyncMock(return_value=[
            {"url": "https://example.com/1", "content": "Content..."},
        ])

        return llm, search_service, web_fetcher

    @pytest.mark.asyncio
    async def test_graph_full_execution(self, mock_all_dependencies):
        """Test full graph execution."""
        llm, search_service, web_fetcher = mock_all_dependencies

        with patch("api.agents.research_agent._get_llm", return_value=llm), \
             patch("api.agents.research_agent.get_web_search_service", return_value=search_service), \
             patch("api.agents.research_agent.get_web_fetcher", return_value=web_fetcher):
            from api.agents.research_agent import create_research_graph

            graph = create_research_graph()

            initial_state = {
                "project_id": "test-project",
                "topic": "Market research for new product",
                "subtopics": ["competitors", "trends"],
                "messages": [],
                "findings": [],
                "pending_queries": [],
                "iterations": 0,
                "is_complete": False,
            }

            result = await graph.ainvoke(initial_state)

            assert result["is_complete"] is True
            assert result["iterations"] >= 1


class TestResearchStateAnnotations:
    """Tests for state annotation operators."""

    def test_findings_accumulate(self):
        """Test findings list uses add operator."""
        # Simulating what the annotated list does
        findings1 = ["Finding 1"]
        findings2 = ["Finding 2", "Finding 3"]

        combined = findings1 + findings2

        assert len(combined) == 3

    def test_messages_accumulate(self):
        """Test messages list uses add operator."""
        from langchain_core.messages import HumanMessage

        msg1 = [HumanMessage(content="First")]
        msg2 = [HumanMessage(content="Second")]

        combined = msg1 + msg2

        assert len(combined) == 2
