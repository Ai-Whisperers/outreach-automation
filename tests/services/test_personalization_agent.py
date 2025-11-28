"""
Service tests for PersonalizationAgent.

Tests cover:
- LangGraph workflow execution
- State transitions
- Message generation
- Validation integration
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestPersonalizationAgentBasics:
    """Basic tests for PersonalizationAgent."""

    def test_agent_initialization(self):
        """Test PersonalizationAgent can be initialized."""
        from api.agents.personalization_agent import PersonalizationAgent

        agent = PersonalizationAgent()
        assert agent is not None

    def test_agent_has_required_nodes(self):
        """Test agent has required workflow nodes."""
        from api.agents.personalization_agent import PersonalizationAgent

        agent = PersonalizationAgent()

        # Check for expected nodes
        expected_nodes = [
            "extract_context",
            "select_pillar",
            "generate_message",
            "validate_message",
        ]

        for node in expected_nodes:
            assert hasattr(agent, node) or hasattr(agent, f"_{node}")


class TestContextExtraction:
    """Tests for context extraction node."""

    @pytest.fixture
    def agent(self):
        """Create PersonalizationAgent."""
        from api.agents.personalization_agent import PersonalizationAgent

        return PersonalizationAgent()

    @pytest.mark.asyncio
    async def test_extract_context_from_prospect(self, agent):
        """Test extracting context from prospect data."""
        prospect_data = {
            "first_name": "John",
            "last_name": "Doe",
            "company": "Acme Corp",
            "title": "VP Marketing",
            "industry": "Technology",
            "personalization_data": {
                "pain_points": ["Manual moderation", "Scaling issues"],
                "metrics": {"revenue": "$5M", "employees": "50"},
            },
        }

        context = await agent.extract_context(prospect_data)

        assert context["first_name"] == "John"
        assert context["company"] == "Acme Corp"
        assert len(context["pain_points"]) > 0

    @pytest.mark.asyncio
    async def test_extract_context_from_brand_brief(self, agent, temp_brand_briefs_dir):
        """Test extracting context from brand brief."""
        prospect_data = {
            "first_name": "Jane",
            "last_name": "Smith",
            "company": "TechCorp",
            "brand_brief_path": str(temp_brand_briefs_dir / "technology" / "techcorp.md"),
        }

        context = await agent.extract_context(prospect_data)

        assert "pain_points" in context
        assert "value_proposition" in context

    @pytest.mark.asyncio
    async def test_extract_context_minimal_data(self, agent):
        """Test extracting context with minimal data."""
        prospect_data = {
            "first_name": "John",
            "last_name": "Doe",
        }

        context = await agent.extract_context(prospect_data)

        assert context["first_name"] == "John"
        # Should handle missing fields gracefully
        assert context.get("company") is None or context.get("company") == ""


class TestPillarSelection:
    """Tests for messaging pillar selection node."""

    @pytest.fixture
    def agent(self):
        """Create PersonalizationAgent."""
        from api.agents.personalization_agent import PersonalizationAgent

        return PersonalizationAgent()

    @pytest.mark.asyncio
    async def test_select_pillar_for_icp(self, agent):
        """Test selecting messaging pillar for ICP type."""
        context = {
            "icp_type": "sme",
            "pain_points": ["Manual moderation"],
            "company": "TechCorp",
        }

        pillar = await agent.select_pillar(context)

        assert "pillar" in pillar or isinstance(pillar, str)

    @pytest.mark.asyncio
    async def test_select_pillar_solopreneur(self, agent):
        """Test pillar selection for solopreneur."""
        context = {"icp_type": "solopreneur"}

        pillar = await agent.select_pillar(context)

        # Solopreneur messaging should focus on simplicity/time-saving
        assert pillar is not None

    @pytest.mark.asyncio
    async def test_select_pillar_enterprise(self, agent):
        """Test pillar selection for enterprise."""
        context = {"icp_type": "enterprise"}

        pillar = await agent.select_pillar(context)

        # Enterprise messaging should focus on strategic value
        assert pillar is not None


class TestMessageGeneration:
    """Tests for message generation node."""

    @pytest.fixture
    def agent_with_mock_llm(self):
        """Create agent with mocked LLM."""
        from api.agents.personalization_agent import PersonalizationAgent

        agent = PersonalizationAgent()
        agent._llm = MagicMock()
        agent._llm.generate = AsyncMock(return_value={
            "message": "Hi John, I noticed Acme's growth...",
            "personalization_elements": ["first_name", "company"],
        })
        return agent

    @pytest.mark.asyncio
    async def test_generate_connection_request(self, agent_with_mock_llm):
        """Test generating LinkedIn connection request."""
        agent = agent_with_mock_llm
        context = {
            "first_name": "John",
            "company": "Acme Corp",
            "pain_points": ["Manual moderation"],
        }

        result = await agent.generate_message(
            context=context,
            message_type="connection_request",
            language="en",
        )

        assert "message" in result
        assert len(result["message"]) <= 200

    @pytest.mark.asyncio
    async def test_generate_cold_email(self, agent_with_mock_llm):
        """Test generating cold email."""
        agent = agent_with_mock_llm
        agent._llm.generate = AsyncMock(return_value={
            "subject": "Quick question about Acme",
            "body": "Hi John, I noticed Acme's impressive growth...",
            "personalization_elements": ["first_name", "company", "pain_point"],
        })

        context = {
            "first_name": "John",
            "company": "Acme Corp",
            "pain_points": ["Manual moderation"],
        }

        result = await agent.generate_message(
            context=context,
            message_type="email_initial",
            language="en",
        )

        assert "subject" in result
        assert "body" in result

    @pytest.mark.asyncio
    async def test_generate_spanish_message(self, agent_with_mock_llm):
        """Test generating message in Spanish."""
        agent = agent_with_mock_llm
        agent._llm.generate = AsyncMock(return_value={
            "message": "Hola Juan, noté el crecimiento de Acme...",
            "personalization_elements": ["first_name", "company"],
        })

        context = {
            "first_name": "Juan",
            "company": "Acme Corp",
        }

        result = await agent.generate_message(
            context=context,
            message_type="connection_request",
            language="es",
        )

        # Should contain Spanish content
        assert "message" in result


class TestMessageValidation:
    """Tests for message validation node."""

    @pytest.fixture
    def agent(self):
        """Create PersonalizationAgent."""
        from api.agents.personalization_agent import PersonalizationAgent

        return PersonalizationAgent()

    @pytest.mark.asyncio
    async def test_validate_valid_message(self, agent):
        """Test validating a valid message."""
        message = {
            "message": "Hi John, I noticed Acme's growth. Worth a quick chat?",
            "message_type": "connection_request",
        }
        context = {
            "first_name": "John",
            "company": "Acme",
        }

        result = await agent.validate_message(message, context)

        assert result["is_valid"] is True

    @pytest.mark.asyncio
    async def test_validate_invalid_message_too_long(self, agent):
        """Test validating message that's too long."""
        message = {
            "message": "x" * 250,
            "message_type": "connection_request",
        }
        context = {}

        result = await agent.validate_message(message, context)

        assert result["is_valid"] is False
        assert any("long" in issue.lower() for issue in result.get("issues", []))

    @pytest.mark.asyncio
    async def test_validate_message_without_cta(self, agent):
        """Test validating message without CTA."""
        message = {
            "message": "Hi John, I noticed Acme's growth. Great work!",
            "message_type": "connection_request",
        }
        context = {}

        result = await agent.validate_message(message, context)

        # Should flag missing CTA
        assert result["is_valid"] is False or len(result.get("suggestions", [])) > 0


class TestMessageRefinement:
    """Tests for message refinement/critique node."""

    @pytest.fixture
    def agent_with_mock_llm(self):
        """Create agent with mocked LLM."""
        from api.agents.personalization_agent import PersonalizationAgent

        agent = PersonalizationAgent()
        agent._llm = MagicMock()
        return agent

    @pytest.mark.asyncio
    async def test_refine_message_on_validation_failure(self, agent_with_mock_llm):
        """Test refining message after validation failure."""
        agent = agent_with_mock_llm
        agent._llm.generate = AsyncMock(return_value={
            "message": "Hi John, noticed Acme's growth. Worth a quick call?",
        })

        original = {
            "message": "x" * 250,  # Too long
            "validation": {
                "is_valid": False,
                "issues": ["Message too long"],
            },
        }

        result = await agent.refine_message(original)

        assert len(result["message"]) <= 200

    @pytest.mark.asyncio
    async def test_critique_improves_personalization(self, agent_with_mock_llm):
        """Test critique step improves personalization."""
        agent = agent_with_mock_llm
        agent._llm.generate = AsyncMock(return_value={
            "critique": "Add company-specific pain point",
            "improved_message": "Hi John, I noticed Acme struggles with content moderation...",
        })

        original = {
            "message": "Hi John, I noticed your company. Let's connect.",
            "personalization_score": 0.3,
        }
        context = {
            "company": "Acme",
            "pain_points": ["Content moderation"],
        }

        result = await agent.critique_message(original, context)

        assert "improved" in result or "critique" in result


class TestFullWorkflow:
    """Tests for full agent workflow execution."""

    @pytest.fixture
    def agent_with_mocks(self):
        """Create fully mocked agent."""
        from api.agents.personalization_agent import PersonalizationAgent

        agent = PersonalizationAgent()
        agent._llm = MagicMock()
        agent._llm.generate = AsyncMock(return_value={
            "message": "Hi John, I noticed Acme's growth in AI. Worth connecting?",
            "subject": "Quick question about Acme",
            "personalization_elements": ["first_name", "company", "industry"],
        })
        return agent

    @pytest.mark.asyncio
    async def test_full_workflow_connection_request(self, agent_with_mocks):
        """Test full workflow for connection request."""
        agent = agent_with_mocks

        prospect = {
            "first_name": "John",
            "last_name": "Doe",
            "company": "Acme Corp",
            "title": "VP Marketing",
            "industry": "Technology",
        }

        result = await agent.generate_personalized_message(
            prospect=prospect,
            message_type="connection_request",
            language="en",
        )

        assert "message" in result
        assert result["validation"]["is_valid"] is True
        assert len(result["message"]) <= 200

    @pytest.mark.asyncio
    async def test_full_workflow_cold_email(self, agent_with_mocks):
        """Test full workflow for cold email."""
        agent = agent_with_mocks
        agent._llm.generate = AsyncMock(return_value={
            "subject": "Quick question about Acme",
            "body": "Hi John, I noticed Acme's impressive growth. We help companies like yours with content operations. Would a quick 15-min call be worth exploring? Best, [Name]",
            "personalization_elements": ["first_name", "company"],
        })

        prospect = {
            "first_name": "John",
            "last_name": "Doe",
            "company": "Acme Corp",
            "title": "VP Marketing",
        }

        result = await agent.generate_personalized_message(
            prospect=prospect,
            message_type="email_initial",
            language="en",
        )

        assert "subject" in result
        assert "body" in result

    @pytest.mark.asyncio
    async def test_workflow_with_brand_brief(self, agent_with_mocks, temp_brand_briefs_dir):
        """Test workflow using brand brief context."""
        agent = agent_with_mocks

        prospect = {
            "first_name": "Jane",
            "last_name": "Smith",
            "company": "TechCorp",
            "brand_brief_path": str(temp_brand_briefs_dir / "technology" / "techcorp.md"),
        }

        result = await agent.generate_personalized_message(
            prospect=prospect,
            message_type="connection_request",
            language="en",
        )

        assert "message" in result

    @pytest.mark.asyncio
    async def test_workflow_retries_on_validation_failure(self, agent_with_mocks):
        """Test workflow retries when validation fails."""
        agent = agent_with_mocks

        # First call returns too long message, second returns valid
        agent._llm.generate = AsyncMock(side_effect=[
            {"message": "x" * 250},  # Too long
            {"message": "Hi John, noticed Acme's growth. Worth connecting?"},
        ])

        prospect = {
            "first_name": "John",
            "company": "Acme",
        }

        result = await agent.generate_personalized_message(
            prospect=prospect,
            message_type="connection_request",
            language="en",
            max_retries=2,
        )

        assert len(result["message"]) <= 200


class TestAgentErrorHandling:
    """Tests for agent error handling."""

    @pytest.fixture
    def agent(self):
        """Create PersonalizationAgent."""
        from api.agents.personalization_agent import PersonalizationAgent

        return PersonalizationAgent()

    @pytest.mark.asyncio
    async def test_handles_llm_error(self, agent):
        """Test handling LLM errors gracefully."""
        agent._llm = MagicMock()
        agent._llm.generate = AsyncMock(side_effect=Exception("API error"))

        prospect = {"first_name": "John", "company": "Acme"}

        with pytest.raises(Exception):
            await agent.generate_personalized_message(
                prospect=prospect,
                message_type="connection_request",
                language="en",
            )

    @pytest.mark.asyncio
    async def test_handles_missing_prospect_data(self, agent):
        """Test handling missing prospect data."""
        prospect = {}  # Empty prospect

        with pytest.raises((ValueError, KeyError)):
            await agent.generate_personalized_message(
                prospect=prospect,
                message_type="connection_request",
                language="en",
            )

    @pytest.mark.asyncio
    async def test_handles_invalid_message_type(self, agent):
        """Test handling invalid message type."""
        prospect = {"first_name": "John"}

        with pytest.raises(ValueError):
            await agent.generate_personalized_message(
                prospect=prospect,
                message_type="invalid_type",
                language="en",
            )


class TestAgentMetrics:
    """Tests for agent performance metrics."""

    @pytest.fixture
    def agent(self):
        """Create PersonalizationAgent."""
        from api.agents.personalization_agent import PersonalizationAgent

        return PersonalizationAgent()

    @pytest.mark.asyncio
    async def test_tracks_generation_time(self, agent):
        """Test agent tracks message generation time."""
        agent._llm = MagicMock()
        agent._llm.generate = AsyncMock(return_value={
            "message": "Hi John, let's connect!",
        })

        prospect = {"first_name": "John", "company": "Acme"}

        result = await agent.generate_personalized_message(
            prospect=prospect,
            message_type="connection_request",
            language="en",
        )

        assert "generation_time_ms" in result
        assert result["generation_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_tracks_personalization_elements(self, agent):
        """Test agent tracks which personalization elements were used."""
        agent._llm = MagicMock()
        agent._llm.generate = AsyncMock(return_value={
            "message": "Hi John at Acme, noticed your AI work...",
            "personalization_elements": ["first_name", "company", "industry"],
        })

        prospect = {
            "first_name": "John",
            "company": "Acme",
            "industry": "AI",
        }

        result = await agent.generate_personalized_message(
            prospect=prospect,
            message_type="connection_request",
            language="en",
        )

        assert "personalization_elements" in result
        assert len(result["personalization_elements"]) > 0
