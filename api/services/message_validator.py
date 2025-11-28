"""
Message Validator Service.

Validates generated outreach messages for:
- Length constraints (LinkedIn connection < 200 chars, etc.)
- Tone matching by ICP
- Cultural fit for es/pt languages
- Personalization depth
- CTA presence
"""

import re
from typing import Any, Literal

from ..logging_config import get_logger

logger = get_logger("services.message_validator")


# =============================================================================
# Constants
# =============================================================================

# Length limits by message type
LENGTH_LIMITS = {
    "connection_request": {"min_chars": 50, "max_chars": 200, "type": "chars"},
    "linkedin_message": {"min_chars": 100, "max_chars": 500, "type": "chars"},
    "email_initial": {"min_words": 150, "max_words": 400, "type": "words"},
    "email_followup_1": {"min_words": 80, "max_words": 250, "type": "words"},
    "email_followup_2": {"min_words": 80, "max_words": 250, "type": "words"},
    "email_followup_3": {"min_words": 50, "max_words": 150, "type": "words"},
    "email_followup_4": {"min_words": 80, "max_words": 200, "type": "words"},
}

# Tone indicators by ICP
TONE_INDICATORS = {
    "solopreneur": {
        "positive": [
            "quick", "easy", "simple", "fast", "save time", "automate",
            "get back", "scale", "without hiring", "yourself",
            "rápido", "fácil", "simple", "automatizar",  # Spanish
            "simples", "automatizar", "economizar",  # Portuguese
        ],
        "negative": [
            "enterprise", "complex", "implementation project",
            "strategic transformation", "governance",
        ],
    },
    "sme": {
        "positive": [
            "roi", "results", "team", "productivity", "cost", "efficiency",
            "measurable", "growth", "output", "department",
            "resultados", "equipo", "productividad", "crecimiento",  # Spanish
            "resultados", "equipe", "produtividade", "crescimento",  # Portuguese
        ],
        "negative": [
            "massive", "transformation", "board approval", "enterprise-wide",
        ],
    },
    "enterprise": {
        "positive": [
            "strategic", "partnership", "methodology", "scale", "transformation",
            "roadmap", "comprehensive", "framework", "stakeholders",
            "estratégico", "metodología", "transformación",  # Spanish
            "estratégico", "metodologia", "transformação",  # Portuguese
        ],
        "negative": [
            "quick fix", "hack", "shortcut", "cheap", "free trial only",
        ],
    },
}

# Cultural patterns by language
CULTURAL_PATTERNS = {
    "en": {
        "greetings": ["Hi", "Hello", "Dear", "Hey"],
        "closings": ["Best", "Regards", "Looking forward", "Thanks", "Cheers"],
        "avoid": [],  # Nothing specific to avoid in English
    },
    "es": {
        "greetings": ["Hola", "Estimado", "Estimada", "Saludos"],
        "closings": [
            "Saludos cordiales", "Atentamente", "Quedo atento",
            "Un abrazo", "Saludos",
        ],
        "avoid": ["Hey", "Cheers", "Best"],  # Too informal/anglicized
    },
    "pt": {
        "greetings": ["Olá", "Oi", "Prezado", "Prezada", "Caro", "Cara"],
        "closings": [
            "Atenciosamente", "Abraços", "Aguardo retorno",
            "Saudações", "Cordialmente",
        ],
        "avoid": ["Hey", "Cheers", "Best"],  # Too informal/anglicized
    },
}

# CTA patterns (regex)
CTA_PATTERNS = [
    # English
    r"\bcall\b", r"\bchat\b", r"\bconnect\b", r"\bmeeting\b",
    r"\bschedule\b", r"\bbook\b", r"\binterested\b", r"\bopen to\b",
    r"\bwould you\b", r"\bworth\b", r"\bminutes?\b", r"\btime\b",
    r"\bdiscuss\b", r"\bexplore\b", r"\btalk\b", r"\bcoffee\b",
    r"\?$",  # Questions often imply CTA
    # Spanish
    r"\bllamada\b", r"\bconectemos\b", r"\binteresa\b", r"\breunión\b",
    r"\bagendar\b", r"\bplaticar\b", r"\bcharlar\b", r"\bminutos?\b",
    # Portuguese
    r"\bligação\b", r"\bconectar\b", r"\binteresse\b", r"\breunião\b",
    r"\bagendar\b", r"\bconversar\b", r"\bminutos?\b",
]


class MessageValidator:
    """
    Validate generated outreach messages meet quality criteria.
    """

    def __init__(self):
        pass

    def validate_message(
        self,
        message: str,
        message_type: str,
        icp_type: str = "sme",
        language: str = "en",
        prospect_context: dict | None = None,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """
        Validate a message against all criteria.

        Args:
            message: The message content
            message_type: Type of message (connection_request, email_initial, etc.)
            icp_type: ICP classification (solopreneur, sme, enterprise)
            language: Target language (en, es, pt)
            prospect_context: Dict with prospect details for personalization check
            subject: Email subject line (for emails)

        Returns:
            {
                "is_valid": bool,
                "overall_score": float (0-1),
                "length": { ... },
                "tone": { ... },
                "cultural_fit": { ... },
                "personalization": { ... },
                "cta": { ... },
                "subject": { ... },  # For emails
                "issues": list[str],
                "suggestions": list[str]
            }
        """
        result = {
            "is_valid": True,
            "overall_score": 0.0,
            "issues": [],
            "suggestions": [],
        }

        # Validate length
        length_result = self.validate_length(message, message_type)
        result["length"] = length_result
        if not length_result["is_valid"]:
            result["is_valid"] = False
            result["issues"].append(length_result.get("issue", "Length invalid"))

        # Validate tone
        tone_result = self.validate_tone(message, icp_type, language)
        result["tone"] = tone_result
        if not tone_result["is_appropriate"]:
            result["suggestions"].append(tone_result.get("suggestion", "Adjust tone"))

        # Validate cultural fit
        cultural_result = self.validate_cultural_fit(message, language)
        result["cultural_fit"] = cultural_result
        if not cultural_result["is_appropriate"]:
            result["issues"].append(cultural_result.get("issue", "Cultural fit issue"))

        # Validate personalization
        personalization_result = self.calculate_personalization_score(
            message, prospect_context or {}
        )
        result["personalization"] = personalization_result
        if personalization_result["score"] < 0.4:
            result["suggestions"].append(
                f"Increase personalization (current: {personalization_result['score']:.0%})"
            )

        # Validate CTA
        cta_result = self.validate_cta(message, language)
        result["cta"] = cta_result
        if not cta_result["has_cta"]:
            result["is_valid"] = False
            result["issues"].append("Missing call-to-action")

        # Validate subject (for emails)
        if message_type.startswith("email") and subject:
            subject_result = self.validate_subject(subject, language)
            result["subject"] = subject_result
            if not subject_result["is_valid"]:
                result["suggestions"].append(subject_result.get("suggestion", ""))

        # Calculate overall score
        scores = [
            1.0 if length_result["is_valid"] else 0.0,
            1.0 if tone_result["is_appropriate"] else 0.5,
            1.0 if cultural_result["is_appropriate"] else 0.5,
            personalization_result["score"],
            1.0 if cta_result["has_cta"] else 0.0,
        ]
        result["overall_score"] = sum(scores) / len(scores)

        # Final validity check
        if result["overall_score"] < 0.6:
            result["is_valid"] = False

        return result

    def validate_length(
        self, message: str, message_type: str
    ) -> dict[str, Any]:
        """Validate message length against limits."""
        limits = LENGTH_LIMITS.get(message_type, {})
        if not limits:
            return {"is_valid": True, "message": "No length limits defined"}

        limit_type = limits.get("type", "chars")

        if limit_type == "chars":
            count = len(message)
            min_limit = limits.get("min_chars", 0)
            max_limit = limits.get("max_chars", float("inf"))
        else:  # words
            count = len(message.split())
            min_limit = limits.get("min_words", 0)
            max_limit = limits.get("max_words", float("inf"))

        is_valid = min_limit <= count <= max_limit

        result = {
            "is_valid": is_valid,
            "count": count,
            "min_limit": min_limit,
            "max_limit": max_limit,
            "unit": limit_type,
        }

        if count < min_limit:
            result["issue"] = f"Too short ({count} {limit_type}, min {min_limit})"
        elif count > max_limit:
            result["issue"] = f"Too long ({count} {limit_type}, max {max_limit})"

        return result

    def validate_tone(
        self, message: str, icp_type: str, language: str
    ) -> dict[str, Any]:
        """Validate message tone matches ICP."""
        indicators = TONE_INDICATORS.get(icp_type, TONE_INDICATORS["sme"])
        message_lower = message.lower()

        positive_matches = []
        negative_matches = []

        # Check for positive indicators
        for indicator in indicators["positive"]:
            if indicator.lower() in message_lower:
                positive_matches.append(indicator)

        # Check for negative indicators
        for indicator in indicators["negative"]:
            if indicator.lower() in message_lower:
                negative_matches.append(indicator)

        is_appropriate = len(negative_matches) == 0

        result = {
            "is_appropriate": is_appropriate,
            "icp_type": icp_type,
            "positive_matches": positive_matches,
            "negative_matches": negative_matches,
        }

        if negative_matches:
            result["suggestion"] = (
                f"Avoid terms for {icp_type}: {', '.join(negative_matches)}"
            )
        elif len(positive_matches) < 2:
            result["suggestion"] = f"Consider adding more {icp_type}-appropriate language"

        return result

    def validate_cultural_fit(
        self, message: str, language: str
    ) -> dict[str, Any]:
        """Validate message is culturally appropriate for language."""
        patterns = CULTURAL_PATTERNS.get(language, CULTURAL_PATTERNS["en"])
        message_lower = message.lower()

        result = {
            "is_appropriate": True,
            "language": language,
            "issues": [],
        }

        # Check for items to avoid
        for avoid_term in patterns["avoid"]:
            if avoid_term.lower() in message_lower:
                result["issues"].append(f"Avoid '{avoid_term}' in {language}")
                result["is_appropriate"] = False

        # For non-English, check for appropriate greeting
        if language != "en":
            has_greeting = any(
                g.lower() in message_lower for g in patterns["greetings"]
            )
            if not has_greeting and len(message) > 200:  # Only for longer messages
                result["issues"].append(
                    f"Consider using a {language} greeting: {', '.join(patterns['greetings'][:3])}"
                )

        if result["issues"]:
            result["issue"] = "; ".join(result["issues"])

        return result

    def calculate_personalization_score(
        self, message: str, context: dict
    ) -> dict[str, Any]:
        """Calculate how personalized the message is."""
        score = 0.0
        elements_found = []
        message_lower = message.lower()

        # Check for company name (25%)
        company = context.get("company", "") or context.get("prospect_company", "")
        if company and company.lower() in message_lower:
            score += 0.25
            elements_found.append("company_name")

        # Check for first name (15%)
        first_name = context.get("first_name", "") or context.get("prospect_name", "")
        if first_name and first_name.lower() in message_lower:
            score += 0.15
            elements_found.append("first_name")

        # Check for role reference (10%)
        role = context.get("role", "") or context.get("prospect_role", "")
        if role:
            role_words = role.lower().split()
            if any(word in message_lower for word in role_words if len(word) > 3):
                score += 0.10
                elements_found.append("role")

        # Check for industry reference (10%)
        industry = context.get("industry", "")
        if industry and industry.lower() in message_lower:
            score += 0.10
            elements_found.append("industry")

        # Check for pain point references (20%)
        pain_points = context.get("pain_points", [])
        for pain_point in pain_points:
            if isinstance(pain_point, str):
                keywords = pain_point.lower().split()[:3]
                if any(kw in message_lower for kw in keywords if len(kw) > 3):
                    score += 0.20
                    elements_found.append("pain_point")
                    break

        # Check for metrics/numbers (10%)
        if re.search(r"\d+%|\d+x|\$[\d,]+|\d+\+", message):
            score += 0.10
            elements_found.append("metric")

        # Check for specific data point (10%)
        if context.get("key_metrics"):
            for metric in context["key_metrics"]:
                if isinstance(metric, str) and len(metric) > 5:
                    # Check if any substantial part of the metric is in the message
                    metric_words = metric.lower().split()
                    if any(w in message_lower for w in metric_words if len(w) > 4):
                        score += 0.10
                        elements_found.append("specific_metric")
                        break

        return {
            "score": min(score, 1.0),
            "elements_found": elements_found,
            "elements_missing": self._get_missing_elements(elements_found),
        }

    def _get_missing_elements(self, found: list[str]) -> list[str]:
        """Get list of personalization elements not found."""
        all_elements = [
            "company_name", "first_name", "role", "industry",
            "pain_point", "metric",
        ]
        return [e for e in all_elements if e not in found]

    def validate_cta(self, message: str, language: str) -> dict[str, Any]:
        """Validate message has a clear call-to-action."""
        message_lower = message.lower()

        cta_found = []
        for pattern in CTA_PATTERNS:
            match = re.search(pattern, message_lower)
            if match:
                cta_found.append(match.group())

        has_cta = len(cta_found) > 0

        # Also check for question mark at end (implicit CTA)
        if message.strip().endswith("?"):
            has_cta = True
            if "question" not in cta_found:
                cta_found.append("question")

        return {
            "has_cta": has_cta,
            "cta_elements": list(set(cta_found)),
            "suggestion": "Add a clear call-to-action" if not has_cta else None,
        }

    def validate_subject(
        self, subject: str, language: str
    ) -> dict[str, Any]:
        """Validate email subject line."""
        result = {
            "is_valid": True,
            "length": len(subject),
            "issues": [],
        }

        # Check length (ideal: 30-60 chars)
        if len(subject) > 60:
            result["issues"].append("Subject too long (>60 chars)")
            result["suggestion"] = "Shorten subject to under 60 characters"
        elif len(subject) < 10:
            result["issues"].append("Subject too short (<10 chars)")
            result["suggestion"] = "Add more context to subject"

        # Check for spam triggers
        spam_triggers = [
            "free", "urgent", "act now", "limited time", "!!!",
            "gratis", "urgente", "ahora",  # Spanish
            "grátis", "urgente", "agora",  # Portuguese
        ]
        for trigger in spam_triggers:
            if trigger.lower() in subject.lower():
                result["issues"].append(f"Avoid spam trigger: '{trigger}'")

        # Check for personalization in subject
        if "{" not in subject and not re.search(r"[A-Z][a-z]+", subject):
            result["suggestion"] = "Consider personalizing the subject line"

        result["is_valid"] = len(result["issues"]) == 0

        return result

    def truncate_linkedin_connection(
        self, message: str, max_chars: int = 200
    ) -> str:
        """Intelligently truncate a LinkedIn connection request."""
        if len(message) <= max_chars:
            return message

        # Try to truncate at sentence boundary
        truncated = message[: max_chars - 3]

        # Find last sentence boundary
        for punct in [".", "!", "?"]:
            last_punct = truncated.rfind(punct)
            if last_punct > max_chars * 0.6:  # Keep at least 60% of content
                return truncated[: last_punct + 1]

        # Fall back to word boundary
        last_space = truncated.rfind(" ")
        if last_space > max_chars * 0.7:
            return truncated[:last_space] + "..."

        return truncated + "..."


def get_message_validator() -> MessageValidator:
    """Factory function to get MessageValidator instance."""
    return MessageValidator()
