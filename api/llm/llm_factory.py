"""
LLM factory for creating LangChain-compatible LLM instances.
"""

import logging

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_llm(
    provider: str = "anthropic",
    temperature: float = 0.7,
    model: str | None = None
):
    """
    Get a LangChain-compatible LLM instance.

    Args:
        provider: "anthropic" or "openai"
        temperature: Sampling temperature (0.0-1.0)
        model: Override default model

    Returns:
        LangChain ChatModel instance
    """

    if provider == "anthropic":
        model_name = model or "claude-sonnet-4-20250514"

        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        llm = ChatAnthropic(
            model=model_name,
            temperature=temperature,
            api_key=settings.anthropic_api_key,
            max_tokens=4096
        )

        logger.info(f"Initialized Anthropic LLM: {model_name}")
        return llm

    elif provider == "openai":
        model_name = model or "gpt-4-turbo-preview"

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=settings.openai_api_key
        )

        logger.info(f"Initialized OpenAI LLM: {model_name}")
        return llm

    else:
        raise ValueError(f"Unknown provider: {provider}")
