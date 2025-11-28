"""
Service tests for AI Client module.

Tests cover:
- Individual AI provider clients
- AI Client Manager with fallback
- Caching integration
- Error handling
- Mock AI client
- Prompt loader
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAnthropicClient:
    """Tests for Anthropic Claude client."""

    @pytest.fixture
    def client(self):
        """Create Anthropic client."""
        with patch("api.services.ai_client.Anthropic") as mock_anthropic:
            from api.services.ai_client import AnthropicClient

            mock_anthropic.return_value = MagicMock()
            return AnthropicClient(api_key="test-key", model="claude-3-opus")

    def test_get_provider_name(self, client):
        """Test provider name."""
        assert client.get_provider_name() == "anthropic"

    @pytest.mark.asyncio
    async def test_generate_success(self, client):
        """Test successful generation."""
        client.client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Generated response")]
        )

        result = await client.generate(
            prompt="Test prompt",
            system="System prompt",
            temperature=0.7,
            max_tokens=1000,
        )

        assert result == "Generated response"
        client.client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_rate_limit(self, client):
        """Test rate limit handling."""
        from anthropic import RateLimitError as AnthropicRateLimitError

        from api.exceptions import AIRateLimitError

        client.client.messages.create.side_effect = AnthropicRateLimitError(
            message="Rate limit", response=MagicMock(), body={}
        )

        with pytest.raises(AIRateLimitError):
            await client.generate(prompt="Test")

    @pytest.mark.asyncio
    async def test_generate_api_error(self, client):
        """Test API error handling."""
        from anthropic import APIError

        from api.exceptions import AIProviderError

        client.client.messages.create.side_effect = APIError(
            message="API Error", request=MagicMock(), body={}
        )

        with pytest.raises(AIProviderError):
            await client.generate(prompt="Test")


class TestOpenAIClient:
    """Tests for OpenAI GPT client."""

    @pytest.fixture
    def client(self):
        """Create OpenAI client."""
        with patch("api.services.ai_client.OpenAI") as mock_openai:
            from api.services.ai_client import OpenAIClient

            mock_openai.return_value = MagicMock()
            return OpenAIClient(api_key="test-key", model="gpt-4")

    def test_get_provider_name(self, client):
        """Test provider name."""
        assert client.get_provider_name() == "openai"

    @pytest.mark.asyncio
    async def test_generate_success(self, client):
        """Test successful generation."""
        client.client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="OpenAI response"))]
        )

        result = await client.generate(
            prompt="Test prompt",
            temperature=0.5,
        )

        assert result == "OpenAI response"

    @pytest.mark.asyncio
    async def test_generate_json_format(self, client):
        """Test JSON response format."""
        client.client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"key": "value"}'))]
        )

        result = await client.generate(
            prompt="Test",
            response_format="json",
        )

        assert result == '{"key": "value"}'

        # Check that response_format was passed
        call_kwargs = client.client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}


class TestGeminiClient:
    """Tests for Google Gemini client."""

    @pytest.fixture
    def client(self):
        """Create Gemini client."""
        with patch("api.services.ai_client.genai") as mock_genai:
            from api.services.ai_client import GeminiClient

            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            client = GeminiClient(api_key="test-key", model="gemini-pro")
            client.model = mock_model
            return client

    def test_get_provider_name(self, client):
        """Test provider name."""
        assert client.get_provider_name() == "gemini"

    @pytest.mark.asyncio
    async def test_generate_success(self, client):
        """Test successful generation."""
        client.model.generate_content_async = AsyncMock(
            return_value=MagicMock(text="Gemini response")
        )

        result = await client.generate(
            prompt="Test prompt",
            system="System prompt",
        )

        assert result == "Gemini response"

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, client):
        """Test system prompt handling."""
        client.model.generate_content_async = AsyncMock(
            return_value=MagicMock(text="Response")
        )

        await client.generate(
            prompt="User prompt",
            system="System instructions",
        )

        # Check that system prompt was prepended
        call_args = client.model.generate_content_async.call_args[0][0]
        assert "System:" in call_args
        assert "User:" in call_args


class TestGroqClient:
    """Tests for Groq client."""

    @pytest.fixture
    def client(self):
        """Create Groq client."""
        with patch("api.services.ai_client.AsyncGroq") as mock_groq:
            from api.services.ai_client import GroqClient

            mock_groq.return_value = MagicMock()
            return GroqClient(api_key="test-key", model="llama3-8b")

    def test_get_provider_name(self, client):
        """Test provider name."""
        assert client.get_provider_name() == "groq"

    @pytest.mark.asyncio
    async def test_generate_success(self, client):
        """Test successful generation."""
        client.client.chat.completions.create = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="Groq response"))]
            )
        )

        result = await client.generate(prompt="Test")

        assert result == "Groq response"


class TestMockAIClient:
    """Tests for Mock AI client."""

    @pytest.fixture
    def client(self):
        """Create Mock client."""
        from api.services.ai_client import MockAIClient

        return MockAIClient()

    def test_get_provider_name(self, client):
        """Test provider name."""
        assert client.get_provider_name() == "mock"

    @pytest.mark.asyncio
    async def test_generate_text(self, client):
        """Test text generation."""
        result = await client.generate(prompt="Test", response_format="text")

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_ideas_json(self, client):
        """Test ideas JSON generation."""
        result = await client.generate(
            prompt="Generate ideas",
            response_format="json",
        )

        parsed = json.loads(result)
        assert "ideas" in parsed

    @pytest.mark.asyncio
    async def test_generate_expand_json(self, client):
        """Test expand JSON generation."""
        result = await client.generate(
            prompt="Expand the idea",
            system="expand",
            response_format="json",
        )

        parsed = json.loads(result)
        assert "concept" in parsed or "scores" in parsed

    @pytest.mark.asyncio
    async def test_generate_validate_json(self, client):
        """Test validate JSON generation."""
        result = await client.generate(
            prompt="Validate this",
            system="validate",
            response_format="json",
        )

        parsed = json.loads(result)
        assert "scores" in parsed or "overall" in parsed

    @pytest.mark.asyncio
    async def test_generate_summary_json(self, client):
        """Test summary JSON generation."""
        result = await client.generate(
            prompt="Summarize this content",
            response_format="json",
        )

        parsed = json.loads(result)
        assert "summary" in parsed or "title" in parsed


class TestAIClientManager:
    """Tests for AI Client Manager."""

    @pytest.fixture
    def manager(self):
        """Create AI Client Manager with mocked settings."""
        with patch("api.services.ai_client.get_settings") as mock_settings:
            mock_config = MagicMock()
            mock_config.ai.primary = "anthropic"
            mock_config.ai.fallback = "openai"
            mock_config.ai.anthropic = MagicMock(model="claude-3", temperature=0.7, max_tokens=4096)
            mock_config.ai.openai = MagicMock(model="gpt-4", temperature=0.7, max_tokens=4096)
            mock_config.anthropic_api_key = "test-anthropic-key"
            mock_config.openai_api_key = "test-openai-key"
            mock_config.groq_api_key = None
            mock_config.gemini_api_key = None
            mock_config.langfuse_public_key = None
            mock_config.langfuse_secret_key = None
            mock_settings.return_value = mock_config

            with patch("api.services.ai_client.AnthropicClient"):
                with patch("api.services.ai_client.OpenAIClient"):
                    from api.services.ai_client import AIClientManager

                    return AIClientManager()

    @pytest.mark.asyncio
    async def test_generate_uses_primary(self, manager):
        """Test generate uses primary client."""
        manager.primary_client = MagicMock()
        manager.primary_client.generate = AsyncMock(return_value="Primary response")

        result = await manager.generate(
            prompt="Test",
            use_cache=False,
        )

        assert result == "Primary response"
        manager.primary_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_falls_back_on_error(self, manager):
        """Test generate falls back to fallback client on error."""
        from api.exceptions import AIProviderError

        manager.primary_client = MagicMock()
        manager.primary_client.generate = AsyncMock(
            side_effect=AIProviderError("Primary failed", provider="anthropic")
        )
        manager.fallback_client = MagicMock()
        manager.fallback_client.generate = AsyncMock(return_value="Fallback response")

        result = await manager.generate(
            prompt="Test",
            use_fallback=True,
            use_cache=False,
        )

        assert result == "Fallback response"

    @pytest.mark.asyncio
    async def test_generate_uses_mock_on_all_failures(self, manager):
        """Test generate uses mock client when all fail."""
        from api.exceptions import AIProviderError

        manager.primary_client = MagicMock()
        manager.primary_client.generate = AsyncMock(
            side_effect=AIProviderError("Primary failed", provider="anthropic")
        )
        manager.fallback_client = MagicMock()
        manager.fallback_client.generate = AsyncMock(
            side_effect=AIProviderError("Fallback failed", provider="openai")
        )
        manager.mock_client = MagicMock()
        manager.mock_client.generate = AsyncMock(return_value="Mock response")

        result = await manager.generate(
            prompt="Test",
            use_cache=False,
        )

        assert result == "Mock response"

    @pytest.mark.asyncio
    async def test_generate_json_success(self, manager):
        """Test JSON generation and parsing."""
        manager.primary_client = MagicMock()
        manager.primary_client.generate = AsyncMock(
            return_value='{"key": "value", "count": 42}'
        )
        manager.primary_client.get_provider_name = MagicMock(return_value="anthropic")

        result = await manager.generate_json(
            prompt="Generate JSON",
            use_cache=False,
        )

        assert result["key"] == "value"
        assert result["count"] == 42

    @pytest.mark.asyncio
    async def test_generate_json_with_markdown_wrapper(self, manager):
        """Test JSON parsing with markdown code blocks."""
        manager.primary_client = MagicMock()
        manager.primary_client.generate = AsyncMock(
            return_value='```json\n{"key": "value"}\n```'
        )
        manager.primary_client.get_provider_name = MagicMock(return_value="anthropic")

        result = await manager.generate_json(
            prompt="Generate JSON",
            use_cache=False,
        )

        assert result["key"] == "value"

    @pytest.mark.asyncio
    async def test_generate_json_invalid_response(self, manager):
        """Test JSON parsing with invalid response."""
        from api.exceptions import AIResponseError

        manager.primary_client = MagicMock()
        manager.primary_client.generate = AsyncMock(return_value="Not valid JSON")
        manager.primary_client.get_provider_name = MagicMock(return_value="anthropic")

        with pytest.raises(AIResponseError):
            await manager.generate_json(
                prompt="Generate JSON",
                use_cache=False,
            )


class TestPromptLoader:
    """Tests for Prompt Loader."""

    @pytest.fixture
    def prompt_loader(self, tmp_path):
        """Create prompt loader with temp directory."""
        from api.services.ai_client import PromptLoader

        # Create test prompts
        prompts_dir = tmp_path / "prompts"
        ideas_dir = prompts_dir / "ideas"
        ideas_dir.mkdir(parents=True)

        # Create test prompt file
        test_prompt = """SYSTEM:
You are an AI assistant for campaign ideas.

USER:
Generate {num_ideas} ideas for {project_name}.
"""
        (ideas_dir / "generate.txt").write_text(test_prompt)

        return PromptLoader(prompts_dir=prompts_dir)

    def test_load_prompt(self, prompt_loader):
        """Test loading a prompt."""
        content = prompt_loader.load("ideas", "generate")

        assert "SYSTEM:" in content
        assert "USER:" in content

    def test_load_prompt_cached(self, prompt_loader):
        """Test prompt caching."""
        # Load twice
        content1 = prompt_loader.load("ideas", "generate")
        content2 = prompt_loader.load("ideas", "generate")

        assert content1 == content2
        assert "ideas/generate" in prompt_loader._cache

    def test_load_prompt_not_found(self, prompt_loader):
        """Test loading non-existent prompt."""
        with pytest.raises(FileNotFoundError):
            prompt_loader.load("ideas", "nonexistent")

    def test_format_prompt(self, prompt_loader):
        """Test formatting prompt with variables."""
        system, user = prompt_loader.format(
            "ideas", "generate",
            num_ideas=5,
            project_name="Test Project",
        )

        assert system is not None
        assert "AI assistant" in system
        assert "5" in user
        assert "Test Project" in user

    def test_format_prompt_splits_system_user(self, prompt_loader):
        """Test prompt splitting into system and user parts."""
        system, user = prompt_loader.format("ideas", "generate")

        assert system is not None
        assert user is not None
        assert "SYSTEM:" not in system
        assert "USER:" not in user


class TestAIClientManagerSingleton:
    """Tests for singleton access."""

    def test_get_ai_manager_returns_same_instance(self):
        """Test singleton pattern."""
        with patch("api.services.ai_client.get_settings") as mock_settings:
            mock_config = MagicMock()
            mock_config.ai.primary = "anthropic"
            mock_config.ai.fallback = "openai"
            mock_config.anthropic_api_key = None
            mock_config.openai_api_key = None
            mock_config.groq_api_key = None
            mock_config.gemini_api_key = None
            mock_config.langfuse_public_key = None
            mock_config.langfuse_secret_key = None
            mock_settings.return_value = mock_config

            # Reset singleton
            import api.services.ai_client
            api.services.ai_client._ai_manager = None

            from api.services.ai_client import get_ai_manager

            manager1 = get_ai_manager()
            manager2 = get_ai_manager()

            assert manager1 is manager2

    def test_get_prompt_loader_returns_same_instance(self):
        """Test prompt loader singleton."""
        # Reset singleton
        import api.services.ai_client
        api.services.ai_client._prompt_loader = None

        from api.services.ai_client import get_prompt_loader

        loader1 = get_prompt_loader()
        loader2 = get_prompt_loader()

        assert loader1 is loader2


class TestAIClientCaching:
    """Tests for AI response caching."""

    @pytest.fixture
    def manager(self):
        """Create manager with mocked cache."""
        with patch("api.services.ai_client.get_settings") as mock_settings:
            mock_config = MagicMock()
            mock_config.ai.primary = "anthropic"
            mock_config.ai.fallback = None
            mock_config.ai.anthropic = MagicMock(temperature=0.2, max_tokens=4096)
            mock_config.anthropic_api_key = "test-key"
            mock_config.openai_api_key = None
            mock_config.groq_api_key = None
            mock_config.gemini_api_key = None
            mock_config.langfuse_public_key = None
            mock_config.langfuse_secret_key = None
            mock_settings.return_value = mock_config

            with patch("api.services.ai_client.AnthropicClient"):
                from api.services.ai_client import AIClientManager

                return AIClientManager()

    @pytest.mark.asyncio
    async def test_cache_hit(self, manager):
        """Test cache hit returns cached response."""
        with patch("api.services.ai_client._get_cache") as mock_cache_fn:
            mock_cache = MagicMock()
            mock_cache.get.return_value = "Cached response"
            mock_cache_fn.return_value = mock_cache

            result = await manager.generate(
                prompt="Test",
                temperature=0.1,  # Low temp enables caching
                use_cache=True,
            )

            assert result == "Cached response"
            mock_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_stores_response(self, manager):
        """Test cache miss stores new response."""
        manager.primary_client = MagicMock()
        manager.primary_client.generate = AsyncMock(return_value="New response")

        with patch("api.services.ai_client._get_cache") as mock_cache_fn:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_fn.return_value = mock_cache

            result = await manager.generate(
                prompt="Test",
                temperature=0.1,
                use_cache=True,
            )

            assert result == "New response"
            mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_disabled_for_high_temp(self, manager):
        """Test caching disabled for high temperature."""
        manager.primary_client = MagicMock()
        manager.primary_client.generate = AsyncMock(return_value="Response")

        with patch("api.services.ai_client._get_cache") as mock_cache_fn:
            mock_cache = MagicMock()
            mock_cache_fn.return_value = mock_cache

            await manager.generate(
                prompt="Test",
                temperature=0.8,  # High temp
                use_cache=True,
            )

            # Cache should not be checked for high temperature
            mock_cache.get.assert_not_called()
