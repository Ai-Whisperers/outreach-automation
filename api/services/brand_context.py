"""
Brand Context Service

Provides Nestlé brand guidelines and visual identity for video generation.
Ensures brand consistency across all generated content.
"""

from dataclasses import dataclass
from typing import Dict, List

from ..logging_config import get_logger

logger = get_logger("brand_context")


@dataclass
class BrandColors:
    """Nestlé brand color palette."""

    primary: str = "#0072CE"  # Nestlé Blue
    secondary: str = "#FFFFFF"  # White
    accent_red: str = "#E30613"  # Nestlé Red
    accent_yellow: str = "#FDB71A"  # Nestlé Yellow
    text_dark: str = "#2C2C2C"  # Dark gray for text
    text_light: str = "#FFFFFF"  # White for text on dark backgrounds


@dataclass
class LogoGuidelines:
    """Nestlé logo placement and usage guidelines."""

    placement: List[str] = None
    size_percentage: str = "10-15%"
    style: str = "clean, modern"
    background: str = "white or transparent"

    def __post_init__(self):
        if self.placement is None:
            self.placement = ["top-right", "bottom-center"]


@dataclass
class VisualStyle:
    """Nestlé visual style guidelines."""

    tone: List[str] = None
    lighting: str = "natural, bright, warm"
    setting: str = "real-life scenarios, authentic locations"
    mood: str = "warm, trustworthy, family-oriented"

    def __post_init__(self):
        if self.tone is None:
            self.tone = ["warm", "family-oriented", "trustworthy", "authentic"]


@dataclass
class Typography:
    """Nestlé typography guidelines."""

    font_family: str = "Nestle Text, sans-serif"
    style: str = "clean, readable, modern"
    weight: str = "regular to bold"


@dataclass
class MarketContext:
    """Market-specific context (e.g., Paraguay)."""

    country: str
    language: List[str]
    cultural_elements: List[str]
    local_settings: List[str]

    @staticmethod
    def paraguay() -> "MarketContext":
        """Get Paraguay market context."""
        return MarketContext(
            country="Paraguay",
            language=["Spanish", "Guaraní"],
            cultural_elements=[
                "Family values",
                "Perseverance (ñeembotavy)",
                "Community spirit",
                "Bilingual culture",
                "Traditional and modern blend",
            ],
            local_settings=[
                "Asunción streets and neighborhoods",
                "Local markets",
                "Family homes",
                "Parks and public spaces",
                "Schools and universities",
            ],
        )


class BrandContext:
    """
    Centralized Nestlé brand context for video generation.
    Provides all brand guidelines and market-specific adaptations.
    """

    def __init__(self, market: str = "paraguay"):
        self.colors = BrandColors()
        self.logo = LogoGuidelines()
        self.visual_style = VisualStyle()
        self.typography = Typography()

        # Load market-specific context
        if market.lower() == "paraguay":
            self.market = MarketContext.paraguay()
        else:
            # Default market context
            self.market = MarketContext(
                country=market, language=["Spanish"], cultural_elements=[], local_settings=[]
            )

    def get_color_palette(self) -> Dict[str, str]:
        """Get Nestlé color palette as dictionary."""
        return {
            "primary": self.colors.primary,
            "secondary": self.colors.secondary,
            "accent_red": self.colors.accent_red,
            "accent_yellow": self.colors.accent_yellow,
            "text_dark": self.colors.text_dark,
            "text_light": self.colors.text_light,
        }

    def get_brand_description(self) -> str:
        """Get comprehensive brand description for prompts."""
        return f"""
NESTLÉ BRAND IDENTITY:
Colors: Primary {self.colors.primary} (Nestlé Blue), White, Red {self.colors.accent_red}, Yellow {self.colors.accent_yellow}
Logo: {self.logo.placement[0]}, {self.logo.size_percentage} of frame, {self.logo.style}
Visual Style: {self.visual_style.tone[0]}, {self.visual_style.lighting}
Mood: {self.visual_style.mood}
Typography: {self.typography.font_family}, {self.typography.style}
        """.strip()

    def get_market_description(self) -> str:
        """Get market-specific description for prompts."""
        return f"""
MARKET CONTEXT ({self.market.country.upper()}):
Languages: {', '.join(self.market.language)}
Cultural Elements: {', '.join(self.market.cultural_elements[:3])}
Settings: {', '.join(self.market.local_settings[:3])}
        """.strip()

    def get_veo_brand_instructions(self) -> str:
        """Get brand instructions formatted for Veo 3.1 prompts."""
        return f"""
BRAND REQUIREMENTS:
- Use Nestlé brand colors: {self.colors.primary} (blue), {self.colors.secondary} (white)
- Include Nestlé logo in {self.logo.placement[0]} ({self.logo.size_percentage} of frame)
- Visual style: {', '.join(self.visual_style.tone)}
- Lighting: {self.visual_style.lighting}
- Setting: {self.market.country} - {', '.join(self.market.local_settings[:2])}
- Mood: {self.visual_style.mood}
        """.strip()

    def validate_prompt(self, prompt: str) -> Dict[str, bool]:
        """
        Validate if a prompt includes required brand elements.

        Returns:
            Dictionary with validation results for each element
        """
        prompt_lower = prompt.lower()

        return {
            "has_colors": any(
                color.lower() in prompt_lower
                for color in [self.colors.primary, "blue", "nestlé blue"]
            ),
            "has_logo": "logo" in prompt_lower or "nestlé" in prompt_lower,
            "has_brand_tone": any(tone.lower() in prompt_lower for tone in self.visual_style.tone),
            "has_market_context": self.market.country.lower() in prompt_lower,
            "has_lighting": any(word in prompt_lower for word in ["light", "bright", "natural"]),
        }

    def is_brand_compliant(self, prompt: str) -> bool:
        """Check if prompt meets minimum brand requirements."""
        validation = self.validate_prompt(prompt)
        # Require at least 3 out of 5 brand elements
        return sum(validation.values()) >= 3


# Singleton instance
_brand_context: BrandContext | None = None


def get_brand_context(market: str = "paraguay") -> BrandContext:
    """Get singleton brand context instance."""
    global _brand_context
    if _brand_context is None:
        _brand_context = BrandContext(market=market)
        logger.info(f"Initialized brand context for market: {market}")
    return _brand_context
