"""
AI Client Abstraction Layer

Provides a unified interface for calling AI providers (Anthropic, OpenAI)
with automatic fallback, retry logic, and error handling.
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import google.generativeai as genai
import httpx
from anthropic import Anthropic, APIError
from anthropic import RateLimitError as AnthropicRateLimitError
from google.api_core import exceptions as google_exceptions
from openai import APIError as OpenAIAPIError
from openai import OpenAI
from openai import RateLimitError as OpenAIRateLimitError

from ..config import get_settings

try:
    from langfuse.callback import CallbackHandler as LangfuseCallbackHandler
except ImportError:
    LangfuseCallbackHandler = None
from ..exceptions import (
    AIProviderError,
    AIRateLimitError,
    AIResponseError,
    AITimeoutError,
)
from ..logging_config import get_logger

logger = get_logger("ai_client")


# Import cache lazily to avoid circular imports
def _get_cache():
    from .cache import get_ai_cache

    return get_ai_cache()


# =============================================================================
# Base AI Client
# =============================================================================


class BaseAIClient(ABC):
    """Abstract base class for AI clients."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = "text",
    ) -> str:
        """
        Generate a response from the AI model.

        Args:
            prompt: User prompt
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            response_format: Expected format ("text" or "json")

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        pass


# =============================================================================
# Anthropic Client
# =============================================================================


class AnthropicClient(BaseAIClient):
    """Anthropic Claude API client."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = Anthropic(api_key=api_key)
        self.model = model
        logger.info(f"Initialized Anthropic client with model: {model}")

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = "text",
    ) -> str:
        """Generate response using Claude."""
        try:
            logger.debug(f"Calling Anthropic API (temp={temperature}, max_tokens={max_tokens})")

            messages = [{"role": "user", "content": prompt}]

            kwargs = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }

            if system:
                kwargs["system"] = system

            response = self.client.messages.create(**kwargs)

            content = response.content[0].text
            logger.debug(f"Received response: {len(content)} characters")

            return content

        except AnthropicRateLimitError as e:
            logger.warning(f"Anthropic rate limit exceeded: {e}")
            raise AIRateLimitError("anthropic")

        except APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise AIProviderError(
                message=str(e), provider="anthropic", error_code="ANTHROPIC_API_ERROR"
            )

        except httpx.TimeoutException as e:
            logger.error(f"Anthropic timeout: {e}")
            raise AITimeoutError("anthropic", timeout_seconds=60)

    def get_provider_name(self) -> str:
        return "anthropic"


# =============================================================================
# OpenAI Client
# =============================================================================


class OpenAIClient(BaseAIClient):
    """OpenAI GPT API client."""

    def __init__(self, api_key: str, model: str = "gpt-4-turbo-preview"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info(f"Initialized OpenAI client with model: {model}")

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = "text",
    ) -> str:
        """Generate response using GPT."""
        try:
            logger.debug(f"Calling OpenAI API (temp={temperature}, max_tokens={max_tokens})")

            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if response_format == "json":
                kwargs["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**kwargs)

            content = response.choices[0].message.content
            logger.debug(f"Received response: {len(content)} characters")

            return content

        except OpenAIRateLimitError as e:
            logger.warning(f"OpenAI rate limit exceeded: {e}")
            raise AIRateLimitError("openai")

        except OpenAIAPIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise AIProviderError(message=str(e), provider="openai", error_code="OPENAI_API_ERROR")

        except httpx.TimeoutException as e:
            logger.error(f"OpenAI timeout: {e}")
            raise AITimeoutError("openai", timeout_seconds=60)

    def get_provider_name(self) -> str:
        return "openai"


# =============================================================================
# Gemini Client
# =============================================================================


class GeminiClient(BaseAIClient):
    """Google Gemini API client."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-pro-latest"):
        genai.configure(api_key=api_key)
        self.model_name = model
        self.model = genai.GenerativeModel(model)
        logger.info(f"Initialized Gemini client with model: {model}")

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = "text",
    ) -> str:
        """Generate response using Gemini."""
        try:
            logger.debug(f"Calling Gemini API (temp={temperature}, max_tokens={max_tokens})")

            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type=(
                    "application/json" if response_format == "json" else "text/plain"
                ),
            )

            # Construct prompt with system instruction if possible,
            # or prepend to user prompt
            full_prompt = prompt
            if system:
                # Gemini supports system instructions in newer models,
                # but for broad compatibility we can also prepend.
                # However, let's try to use the system_instruction if initializing model,
                # but here we already initialized it.
                # We can pass system instruction to GenerativeModel constructor,
                # but we are reusing the instance.
                # For per-request system prompt, it's best to prepend or use chat history.
                # Simple approach: Prepend system prompt
                full_prompt = f"System: {system}\n\nUser: {prompt}"

            response = await self.model.generate_content_async(
                full_prompt, generation_config=generation_config
            )

            content = response.text
            logger.debug(f"Received response: {len(content)} characters")

            return content

        except google_exceptions.ResourceExhausted as e:
            logger.warning(f"Gemini rate limit exceeded: {e}")
            raise AIRateLimitError("gemini")

        except google_exceptions.GoogleAPICallError as e:
            logger.error(f"Gemini API error: {e}")
            raise AIProviderError(message=str(e), provider="gemini", error_code="GEMINI_API_ERROR")

        except Exception as e:
            logger.error(f"Gemini unexpected error: {e}")
            raise AIProviderError(
                f"Gemini error: {e}", provider="gemini", error_code="GEMINI_ERROR"
            )

    def get_provider_name(self):
        return "gemini"


# =============================================================================
# Groq Client
# =============================================================================


class GroqClient(BaseAIClient):
    """Groq API client (Llama models via cloud)."""

    def __init__(self, api_key: str, model: str = "llama-3.1-8b-instant"):
        from groq import AsyncGroq

        self.client = AsyncGroq(api_key=api_key)
        self.model = model

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = "text",
    ):
        """Generate response using Groq."""
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return response.choices[0].message.content

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Groq API error: {error_msg}")

            # Handle rate limits
            if "rate" in error_msg.lower() or "429" in error_msg:
                raise AIRateLimitError(f"Rate limit exceeded for groq: {error_msg}")

            # Handle timeouts
            if "timeout" in error_msg.lower():
                raise AITimeoutError(f"Groq request timed out: {error_msg}")

            # Generic error
            raise AIProviderError(f"Groq API error: {error_msg}", provider="groq")

    def get_provider_name(self):
        return "groq"


# =============================================================================
# Ollama Client (Local LLM)
# =============================================================================


class OllamaClient(BaseAIClient):
    """Ollama local LLM client."""

    def __init__(self, model: str = "llama3.1:8b"):
        import ollama

        self.client = ollama
        self.model = model

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = "text",
    ):
        """Generate response using Ollama (local)."""
        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            )

            return response["message"]["content"]

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ollama error: {error_msg}")

            # Handle connection errors (Ollama not running)
            if "connection" in error_msg.lower() or "refused" in error_msg.lower():
                raise AIProviderError(
                    f"Ollama not running or not accessible: {error_msg}", provider="ollama"
                )

            # Generic error
            raise AIProviderError(f"Ollama error: {error_msg}", provider="ollama")

    def get_provider_name(self):
        return "ollama"


# =============================================================================
# AI Client Manager
# =============================================================================


class AIClientManager:
    """
    Manages AI clients with fallback support.

    Provides automatic failover between primary and fallback providers.
    """

    def __init__(self):
        self.settings = get_settings()
        self.config = (
            get_settings()
        )  # Alias for backward compatibility if needed, or just use settings
        self.primary_client: BaseAIClient | None = None
        self.fallback_client: BaseAIClient | None = None
        self.langfuse_callback: CallbackHandler | None = None
        self._initialize_clients()
        self._initialize_langfuse()

    def _initialize_clients(self):
        """Initialize primary and fallback clients based on configuration."""
        primary_provider = self.config.ai.primary
        fallback_provider = self.config.ai.fallback

        logger.info(
            f"Initializing AI clients: primary={primary_provider}, fallback={fallback_provider}"
        )

        # Initialize primary client
        if primary_provider == "ollama":
            try:
                self.primary_client = OllamaClient(
                    model=self.config.ai.ollama.model if self.config.ai.ollama else "llama3.1:8b"
                )
                logger.info(f"✅ Initialized Ollama (local) as primary")
            except Exception as e:
                logger.warning(f"Failed to initialize Ollama: {e}. Will use fallback.")

        elif primary_provider == "groq":
            if self.settings.groq_api_key:
                self.primary_client = GroqClient(
                    api_key=self.settings.groq_api_key,
                    model=(
                        self.config.ai.groq.model if self.config.ai.groq else "llama-3.1-8b-instant"
                    ),
                )
                logger.info(f"✅ Initialized Groq as primary")
            else:
                logger.warning("Groq API key not configured")

        elif primary_provider == "anthropic":
            if self.settings.anthropic_api_key:
                self.primary_client = AnthropicClient(
                    api_key=self.settings.anthropic_api_key,
                    model=(
                        self.config.ai.anthropic.model
                        if self.config.ai.anthropic
                        else "claude-3-opus-20240229"
                    ),
                )
                logger.info(f"✅ Initialized Anthropic as primary")
            else:
                logger.warning("Anthropic API key not configured")

        elif primary_provider == "openai":
            if self.settings.openai_api_key:
                self.primary_client = OpenAIClient(
                    api_key=self.settings.openai_api_key,
                    model=(
                        self.config.ai.openai.model
                        if self.config.ai.openai
                        else "gpt-4-turbo-preview"
                    ),
                )
                logger.info(f"✅ Initialized OpenAI as primary")
            else:
                logger.warning("OpenAI API key not configured")

        elif primary_provider == "gemini":
            if self.settings.gemini_api_key:
                self.primary_client = GeminiClient(
                    api_key=self.settings.gemini_api_key,
                    model=(
                        self.config.ai.gemini.model
                        if self.config.ai.gemini
                        else "gemini-1.5-pro-latest"
                    ),
                )
                logger.info(f"✅ Initialized Gemini as primary")
            else:
                logger.warning("Gemini API key not configured")

        # Initialize fallback client
        if fallback_provider == "groq":
            if self.settings.groq_api_key:
                self.fallback_client = GroqClient(
                    api_key=self.settings.groq_api_key,
                    model=(
                        self.config.ai.groq.model if self.config.ai.groq else "llama-3.1-8b-instant"
                    ),
                )
                logger.info(f"✅ Initialized Groq as fallback")
            else:
                logger.warning("Groq API key not configured (fallback unavailable)")

        elif fallback_provider == "openai":
            if self.settings.openai_api_key:
                self.fallback_client = OpenAIClient(
                    api_key=self.settings.openai_api_key,
                    model=self.config.ai.openai.model if self.config.ai.openai else "gpt-3.5-turbo",
                )
                logger.info(f"✅ Initialized OpenAI as fallback")
            else:
                logger.warning("OpenAI API key not configured (fallback unavailable)")

        elif fallback_provider == "anthropic":
            if self.settings.anthropic_api_key:
                self.fallback_client = AnthropicClient(
                    api_key=self.settings.anthropic_api_key,
                    model=(
                        self.config.ai.anthropic.model
                        if self.config.ai.anthropic
                        else "claude-3-opus-20240229"
                    ),
                )
                logger.info(f"✅ Initialized Anthropic as fallback")
            else:
                logger.warning("Anthropic API key not configured (fallback unavailable)")

        if not self.primary_client and not self.fallback_client:
            logger.warning("⚠️ No AI clients initialized!")

        # Always initialize mock client for emergency fallback
        self.mock_client = MockAIClient()

    def _initialize_langfuse(self):
        """Initialize Langfuse callback handler if configured."""
        if not LangfuseCallbackHandler:
            return

        if self.settings.langfuse_public_key and self.settings.langfuse_secret_key:
            try:
                self.langfuse_callback = LangfuseCallbackHandler(
                    public_key=self.settings.langfuse_public_key,
                    secret_key=self.settings.langfuse_secret_key,
                    host=self.settings.langfuse_host,
                )
                logger.info("Langfuse integration enabled")
            except Exception as e:
                logger.error(f"Failed to initialize Langfuse: {e}")

        # Always initialize mock client for fallback/emergency
        self.mock_client = MockAIClient()

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str = "text",
        use_fallback: bool = True,
        use_cache: bool = True,
    ) -> str:
        """
        Generate AI response with automatic fallback and caching.
        """
        # Use defaults from config
        # Use defaults from config
        if temperature is None:
            # Try to get from primary provider config, else default to 0.7
            if self.config.ai.primary == "anthropic" and self.config.ai.anthropic:
                temperature = self.config.ai.anthropic.temperature
            elif self.config.ai.primary == "openai" and self.config.ai.openai:
                temperature = self.config.ai.openai.temperature
            elif self.config.ai.primary == "gemini" and self.config.ai.gemini:
                temperature = self.config.ai.gemini.temperature
            else:
                temperature = 0.7

        if max_tokens is None:
            # Try to get from primary provider config, else default to 4096
            if self.config.ai.primary == "anthropic" and self.config.ai.anthropic:
                max_tokens = self.config.ai.anthropic.max_tokens
            elif self.config.ai.primary == "openai" and self.config.ai.openai:
                max_tokens = self.config.ai.openai.max_tokens
            elif self.config.ai.primary == "gemini" and self.config.ai.gemini:
                max_tokens = self.config.ai.gemini.max_tokens
            else:
                max_tokens = 4096

        # Check cache first (only for deterministic requests)
        cache = _get_cache()
        if use_cache and temperature < 0.3:  # Only cache low-temperature responses
            cached_response = cache.get(prompt, system, temperature, max_tokens)
            if cached_response is not None:
                logger.debug("Using cached AI response")
                return cached_response

        response = None

        # Try primary client
        if self.primary_client:
            try:
                response = await self.primary_client.generate(
                    prompt=prompt,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
            except (AIRateLimitError, AITimeoutError, AIProviderError) as e:
                if use_fallback and self.fallback_client:
                    logger.warning(f"Primary provider failed, using fallback: {e}")
                elif self.mock_client:
                    logger.warning(f"Primary provider failed, using mock: {e}")
                else:
                    raise

        # Try fallback client if primary failed or unavailable
        if response is None and self.fallback_client:
            try:
                response = await self.fallback_client.generate(
                    prompt=prompt,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
            except (AIRateLimitError, AITimeoutError, AIProviderError) as e:
                if self.mock_client:
                    logger.warning(f"Fallback provider failed, using mock: {e}")
                else:
                    raise

        # Try mock client if everything else failed
        if response is None and self.mock_client:
            response = await self.mock_client.generate(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

        if response is None:
            # If we get here, we really have no options (no mock client initialized?)
            # But we initialize it in __init__ if no providers.
            # However, if providers exist but fail, we might not have initialized mock_client if we didn't add logic in __init__
            # Let's force initialize it if needed or just instantiate it here.
            logger.warning("All providers failed, using emergency Mock Client")
            response = await MockAIClient().generate(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

        # Cache the response
        if use_cache and temperature < 0.3:
            cache.set(prompt, response, system, temperature, max_tokens)

        return response

    async def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        use_fallback: bool = True,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Generate AI response and parse as JSON.
        """
        response = await self.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json",
            use_fallback=use_fallback,
            use_cache=use_cache,
        )

        try:
            # Try to extract JSON from response
            # Handle cases where model wraps in markdown code blocks
            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            # Try direct parse first
            try:
                return json.loads(content.strip())
            except json.JSONDecodeError:
                # If direct parse fails, try to extract JSON using regex
                logger.warning("Direct JSON parse failed, attempting regex extraction...")
                import re

                # Try to find JSON object (starts with {, ends with })
                json_match = re.search(r"\{.*\}", content.strip(), re.DOTALL)
                if json_match:
                    try:
                        extracted = json_match.group()
                        parsed = json.loads(extracted)
                        logger.info("Successfully extracted JSON object from response")
                        return parsed
                    except json.JSONDecodeError:
                        pass

                # Try to find JSON array (starts with [, ends with ])
                array_match = re.search(r"\[.*\]", content.strip(), re.DOTALL)
                if array_match:
                    try:
                        extracted = array_match.group()
                        parsed = json.loads(extracted)
                        logger.info("Successfully extracted JSON array from response")
                        return parsed
                    except json.JSONDecodeError:
                        pass

                # If all extraction attempts fail, re-raise original error
                raise

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response was: {response[:500]}")
            raise AIResponseError(
                provider=(
                    self.primary_client.get_provider_name() if self.primary_client else "unknown"
                ),
                reason=f"Invalid JSON: {e}",
            )


class MockAIClient(BaseAIClient):
    """Mock AI client for testing or when quotas are exceeded."""

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: str = "text",
    ) -> str:
        """Generate mock response."""
        logger.info("Generating MOCK response")

        if response_format == "json":
            # Return dummy JSON based on prompt content keywords
            # Check for ideas/brainstorm FIRST as they might contain "summary" in context
            if "ideas" in prompt.lower() or "brainstorm" in (system or "").lower():
                return json.dumps(
                    {
                        "ideas": [
                            {
                                "title": "Ueno para Todos",
                                "description": "A campaign focusing on accessibility for all Paraguayans.",
                                "rationale": "Aligns with financial inclusion mission.",
                            },
                            {
                                "title": "El Futuro es Hoy",
                                "description": "Showcasing the futuristic digital terminals.",
                                "rationale": "Highlights technological leadership.",
                            },
                            {
                                "title": "Sin Fronteras",
                                "description": "Using the app anywhere in the world.",
                                "rationale": "Emphasizes digital freedom.",
                            },
                        ]
                    }
                )
            elif "expand" in prompt.lower() or "expand" in (system or "").lower():
                return json.dumps(
                    {
                        "concept": "Expanded concept details...",
                        "insight": "Deep consumer insight...",
                        "execution": {
                            "headline": "The future is now",
                            "visual": "Futuristic banking terminal",
                            "copy": "Experience the revolution.",
                        },
                        "scores": {
                            "diferenciacion": 8,
                            "relevancia_cultural": 9,
                            "claridad_insight": 8,
                            "ejecutabilidad": 9,
                            "potencial_viral": 7,
                            "memorabilidad": 8,
                            "versatilidad": 9,
                            "alineacion_marca": 10,
                            "potencial_pr": 8,
                            "escalabilidad": 9,
                        },
                        "strengths": ["Strong brand alignment", "High feasibility"],
                        "weaknesses": ["Requires budget"],
                        "recommendation": "Proceed with pilot.",
                    }
                )
            elif "validate" in prompt.lower() or "validate" in (system or "").lower():
                return json.dumps(
                    {
                        "scores": {"clarity": 9, "feasibility": 8},
                        "overall": 8.5,
                        "strengths": ["Clear message", "Good fit"],
                        "weaknesses": ["None"],
                        "suggestions": ["Go for it"],
                    }
                )
            elif "cultural" in prompt.lower() or "cultural" in (system or "").lower():
                return json.dumps(
                    {
                        "cultural_score": 9,
                        "positives": ["Respects local customs"],
                        "concerns": [],
                        "suggestions": [],
                        "approved": True,
                    }
                )
            elif "statistics" in prompt.lower() or "statistics" in (system or "").lower():
                return json.dumps(
                    {
                        "statistics": [
                            {"text": "Ueno Bank has 2 million users", "source": "Mock Data"},
                            {"text": "50% market growth in 2024", "source": "Mock Data"},
                            {"text": "#1 Digital Bank in Paraguay", "source": "Mock Data"},
                        ]
                    }
                )
            elif "summary" in prompt.lower() or "summarize" in (system or "").lower():
                return json.dumps(
                    {
                        "title": "Mock Research Summary",
                        "summary": "This is a mock summary of the research content. Ueno Bank is a leading digital bank in Paraguay focused on financial inclusion and technology.",
                        "key_points": [
                            "Digital first approach",
                            "Financial inclusion",
                            "Rapid growth",
                        ],
                        "statistics": [{"text": "2M users", "source": "Mock"}],
                        "relevance_score": 9.0,
                        "source_type": "news_article",
                    }
                )
            elif "refine" in prompt.lower() or "refine" in (system or "").lower():
                return json.dumps(
                    {
                        "ideas": [
                            {
                                "title": "Ueno para Todos (Refined)",
                                "description": "A refined campaign focusing on accessibility for all Paraguayans, emphasizing zero fees and 24/7 access.",
                                "rationale": "Stronger value proposition based on critique, highlighting inclusivity.",
                            },
                            {
                                "title": "El Futuro es Hoy (Refined)",
                                "description": "Showcasing the futuristic digital terminals with real user testimonials to build trust.",
                                "rationale": "Adds social proof to the tech angle to make it more relatable.",
                            },
                            {
                                "title": "Sin Fronteras (Refined)",
                                "description": "Using the app anywhere in the world, highlighting travel benefits and global acceptance.",
                                "rationale": "Expands on the freedom concept with concrete examples.",
                            },
                        ]
                    }
                )
            elif "score" in prompt.lower() or "critique" in (system or "").lower():
                # For scoring/critique
                return json.dumps(
                    {
                        "scores": {
                            "Diferenciación": 8,
                            "Autenticidad": 9,
                            "Potencial Viral": 7,
                            "Conexión Emocional": 8,
                            "Ejecutabilidad": 9,
                            "Esencia de Marca": 10,
                            "Target Connection": 8,
                            "Formato Digital": 9,
                            "Memorable": 7,
                            "Valor al Consumidor": 9,
                        },
                        "critique": "Strong idea with good brand alignment.",
                    }
                )
            elif "video" in prompt.lower():
                return json.dumps(
                    {
                        "video_prompt": "Cinematic shot of a modern digital bank terminal in Asuncion, golden hour lighting, 4k.",
                        "style": "Modern, Tech, Warm",
                    }
                )
            else:
                return json.dumps({"error": "Unknown mock request type"})

        return "This is a mock text response from the AI."

    def get_provider_name(self) -> str:
        return "mock"

    async def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """
        Generate AI response and parse as JSON.

        Args:
            prompt: User prompt
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Max tokens

        Returns:
            Parsed JSON response
        """
        response = await self.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json",
        )

        try:
            # Try to extract JSON from response
            # Handle cases where model wraps in markdown code blocks
            content = response.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            return json.loads(content.strip())

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response was: {response[:500]}")
            raise AIResponseError(
                provider=(
                    self.primary_client.get_provider_name() if self.primary_client else "unknown"
                ),
                reason=f"Invalid JSON: {e}",
            )


# =============================================================================
# Prompt Loader
# =============================================================================


class PromptLoader:
    """
    Loads and formats AI prompts from files.
    """

    def __init__(self, prompts_dir: Path | None = None):
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent.parent / "config" / "prompts"
        self.prompts_dir = prompts_dir
        self._cache: dict[str, str] = {}

    def load(self, category: str, name: str) -> str:
        """
        Load a prompt from file.

        Args:
            category: Prompt category (research, brief, ideas, etc.)
            name: Prompt name (without .txt extension)

        Returns:
            Prompt content
        """
        cache_key = f"{category}/{name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt_path = self.prompts_dir / category / f"{name}.txt"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")

        content = prompt_path.read_text(encoding="utf-8")
        self._cache[cache_key] = content

        return content

    def format(self, category: str, name: str, **kwargs) -> tuple[str | None, str]:
        """
        Load and format a prompt with variables.

        Args:
            category: Prompt category
            name: Prompt name
            **kwargs: Variables to substitute

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        content = self.load(category, name)

        # Split into SYSTEM and USER parts
        system_prompt = None
        user_prompt = content

        if "SYSTEM:" in content and "USER:" in content:
            parts = content.split("USER:", 1)
            system_part = parts[0]
            user_prompt = parts[1].strip()

            if "SYSTEM:" in system_part:
                system_prompt = system_part.split("SYSTEM:", 1)[1].strip()

        # Format with variables
        for key, value in kwargs.items():
            placeholder = f"{{{key}}}"
            if system_prompt:
                system_prompt = system_prompt.replace(placeholder, str(value))
            user_prompt = user_prompt.replace(placeholder, str(value))

        return system_prompt, user_prompt


# =============================================================================
# Singleton Access
# =============================================================================

_ai_manager: AIClientManager | None = None
_prompt_loader: PromptLoader | None = None


def get_ai_manager() -> AIClientManager:
    """Get singleton AI client manager."""
    global _ai_manager
    if _ai_manager is None:
        _ai_manager = AIClientManager()
    return _ai_manager


def get_prompt_loader() -> PromptLoader:
    """Get singleton prompt loader."""
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader
