"""
Personalization Agent

A LangGraph-based agent for generating, critiquing, and refining
personalized outreach messages using brand brief data.

Workflow:
1. Extract Context - Parse brand brief, extract pain points, metrics
2. Select Pillar - Choose messaging pillar based on ICP
3. Generate Draft - AI generates initial message
4. Critique - Review for quality, personalization depth
5. Refine - Improve based on critique (loops back to critique)
6. Validate - Check length, tone, cultural fit
7. Format Output - Final formatting
"""

from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from ..logging_config import get_logger
from ..services.ai_client import get_ai_manager

logger = get_logger("personalization_agent")


# =============================================================================
# Type Definitions
# =============================================================================

ICPType = Literal["solopreneur", "sme", "enterprise"]
LanguageType = Literal["en", "es", "pt"]
MessageTypeType = Literal[
    "connection_request",
    "linkedin_message",
    "email_initial",
    "email_followup_1",
    "email_followup_2",
    "email_followup_3",
    "email_followup_4",
]


# =============================================================================
# State Definition
# =============================================================================


class PersonalizationState(TypedDict):
    """State for the Personalization Agent."""

    # Input Context
    brand_brief: dict  # Parsed brand brief data
    prospect_name: str  # Contact's first name
    prospect_full_name: str  # Full name
    prospect_role: str  # Contact's job title
    prospect_company: str  # Company name
    icp_type: ICPType  # solopreneur, sme, enterprise
    industry: str  # Industry category
    language: LanguageType  # Target language (en, es, pt)

    # Message Configuration
    message_type: MessageTypeType
    max_length: int  # Character/word limit

    # Extracted Personalization Context
    pain_points: list[str]  # Top 3 pain points
    key_metrics: list[str]  # Relevant metrics/stats
    value_proposition: str  # Tailored value prop
    competitive_angle: str  # Competitive context
    talking_points: list[str]  # Opening hooks

    # Messaging Pillar
    messaging_pillar: str  # Selected pillar
    pillar_key_message: str  # Key message for pillar

    # Generation Phase
    draft_message: str  # Initial generated message
    draft_subject: str  # For emails
    critique: str  # Critique feedback
    refined_message: str  # After refinement
    refined_subject: str  # Refined subject

    # Validation Phase
    validation_result: dict  # Validation scores
    is_valid: bool  # Passes all checks
    final_message: str  # Final output
    final_subject: str  # Final subject

    # Iteration Control
    iteration_count: int
    max_iterations: int

    # Errors
    errors: list[str]


# =============================================================================
# Constants
# =============================================================================

# Messaging pillars by ICP (from messaging-framework.md)
PILLAR_MATRIX = {
    "solopreneur": {
        "primary": "speed_simplicity",
        "secondary": "roi_results",
        "key_message": "Get your time back this month. Scale without hiring.",
        "tone": "casual, time-focused, ROI-driven",
    },
    "sme": {
        "primary": "roi_results",
        "secondary": "human_centered",
        "key_message": "Cut costs, boost output, keep your team happy.",
        "tone": "professional, metrics-focused, team-oriented",
    },
    "enterprise": {
        "primary": "comprehensive_partnership",
        "secondary": "human_centered",
        "key_message": "Strategic AI transformation with proven methodology.",
        "tone": "strategic, partnership-focused, process-oriented",
    },
}

# Message length limits
LENGTH_LIMITS = {
    "connection_request": {"max_chars": 200, "min_chars": 50},
    "linkedin_message": {"max_chars": 500, "min_chars": 100},
    "email_initial": {"max_words": 400, "min_words": 150},
    "email_followup_1": {"max_words": 250, "min_words": 80},
    "email_followup_2": {"max_words": 250, "min_words": 80},
    "email_followup_3": {"max_words": 150, "min_words": 50},
    "email_followup_4": {"max_words": 200, "min_words": 80},
}

# Language-specific greetings
GREETINGS = {
    "en": {"formal": "Hi", "casual": "Hey"},
    "es": {"formal": "Hola", "casual": "Hola"},
    "pt": {"formal": "Olá", "casual": "Oi"},
}


# =============================================================================
# Nodes
# =============================================================================


async def extract_context_node(state: PersonalizationState) -> dict:
    """Extract personalization elements from brand brief."""
    logger.info(f"Extracting context for {state['prospect_company']}")

    brief = state.get("brand_brief", {})
    updates = {"errors": []}

    try:
        # Extract pain points (top 3)
        pain_points = brief.get("key_pain_points", [])[:3]
        updates["pain_points"] = pain_points

        # Extract key metrics
        metrics = []
        overview = brief.get("company_overview", {})
        if overview.get("revenue"):
            metrics.append(f"Revenue: {overview['revenue']}")
        if overview.get("employees"):
            metrics.append(f"Employees: {overview['employees']}")

        digital = brief.get("digital_presence", {})
        for key, value in digital.get("metrics", {}).items():
            metrics.append(f"{key.replace('_', ' ').title()}: {value}")
        updates["key_metrics"] = metrics[:5]

        # Get value proposition
        messaging = brief.get("messaging_strategy", {})
        value_props = messaging.get("value_propositions", {})
        role_lower = state.get("prospect_role", "").lower()

        # Try to match role to value proposition
        value_prop = ""
        for audience, prop in value_props.items():
            if any(kw in role_lower for kw in audience.lower().split("/")):
                value_prop = prop
                break
        if not value_prop and value_props:
            value_prop = list(value_props.values())[0]
        updates["value_proposition"] = value_prop

        # Get competitive angle
        updates["competitive_angle"] = messaging.get("competitive_angle", "")

        # Get talking points (opening hooks)
        talking_points = []
        for point in brief.get("talking_points", []):
            if isinstance(point, dict):
                talking_points.append(point.get("content", ""))
            else:
                talking_points.append(str(point))
        updates["talking_points"] = talking_points[:3]

        logger.info(
            f"Extracted: {len(pain_points)} pain points, "
            f"{len(metrics)} metrics, {len(talking_points)} talking points"
        )

    except Exception as e:
        logger.error(f"Error extracting context: {e}")
        updates["errors"] = [f"Context extraction error: {str(e)}"]

    return updates


async def select_pillar_node(state: PersonalizationState) -> dict:
    """Select appropriate messaging pillar based on ICP and role."""
    logger.info(f"Selecting pillar for ICP: {state['icp_type']}")

    icp = state.get("icp_type", "sme")
    pillar_config = PILLAR_MATRIX.get(icp, PILLAR_MATRIX["sme"])

    return {
        "messaging_pillar": pillar_config["primary"],
        "pillar_key_message": pillar_config["key_message"],
    }


async def generate_draft_node(state: PersonalizationState) -> dict:
    """Generate initial message draft using AI."""
    logger.info(f"Generating {state['message_type']} draft")

    ai = get_ai_manager()

    # Build the system prompt
    system_prompt = _build_system_prompt(state)

    # Build the user prompt
    user_prompt = _build_user_prompt(state)

    try:
        # Generate message
        if state["message_type"].startswith("email"):
            # For emails, generate subject and body
            response = await ai.generate_json(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.7,
            )

            return {
                "draft_message": response.get("body", ""),
                "draft_subject": response.get("subject", ""),
                "iteration_count": 0,
            }
        else:
            # For LinkedIn, just generate message
            response = await ai.generate(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.7,
                max_tokens=500,
            )

            return {
                "draft_message": response.strip(),
                "draft_subject": "",
                "iteration_count": 0,
            }

    except Exception as e:
        logger.error(f"Error generating draft: {e}")
        return {
            "draft_message": "",
            "draft_subject": "",
            "errors": state.get("errors", []) + [f"Generation error: {str(e)}"],
        }


async def critique_node(state: PersonalizationState) -> dict:
    """Critique the generated message for quality."""
    logger.info("Critiquing message draft")

    ai = get_ai_manager()

    message = state.get("refined_message") or state.get("draft_message", "")
    if not message:
        return {"critique": "No message to critique."}

    critique_system = """You are an expert B2B copywriter and outreach specialist.
Critique this outreach message for:
1. Personalization depth - Does it use specific company/role details?
2. Value proposition clarity - Is the benefit clear?
3. Tone appropriateness - Does it match the target persona?
4. Length appropriateness - Is it right for the channel?
5. Call-to-action effectiveness - Is there a clear next step?
6. Cultural fit - Is it appropriate for the target language/region?

Be specific and actionable in your critique. Focus on improvements."""

    critique_prompt = f"""
Message Type: {state['message_type']}
Target: {state['prospect_name']} - {state['prospect_role']} at {state['prospect_company']}
ICP: {state['icp_type']}
Language: {state['language']}
Pillar: {state['messaging_pillar']}

Draft Message:
{message}

Personalization Context:
- Pain Points: {state.get('pain_points', [])}
- Metrics: {state.get('key_metrics', [])}
- Value Prop: {state.get('value_proposition', '')}

Provide specific critique and improvement suggestions.
Focus on what should be improved, not what's already good.
"""

    try:
        critique = await ai.generate(
            prompt=critique_prompt,
            system=critique_system,
            temperature=0.4,
        )
        return {"critique": critique}
    except Exception as e:
        logger.error(f"Error critiquing: {e}")
        return {"critique": f"Critique error: {str(e)}"}


async def refine_node(state: PersonalizationState) -> dict:
    """Refine message based on critique."""
    logger.info("Refining message based on critique")

    ai = get_ai_manager()

    current_message = state.get("refined_message") or state.get("draft_message", "")
    current_subject = state.get("refined_subject") or state.get("draft_subject", "")

    refine_system = """You are an expert B2B copywriter.
Improve the message based on the critique provided.
Maintain the core value proposition while addressing all feedback.
Preserve personalization elements and keep within length limits.
Do NOT add generic filler - every sentence should add value."""

    limits = LENGTH_LIMITS.get(state["message_type"], {})
    limit_str = ""
    if "max_chars" in limits:
        limit_str = f"Character limit: {limits['max_chars']} (STRICT for LinkedIn)"
    elif "max_words" in limits:
        limit_str = f"Word limit: {limits['max_words']}"

    refine_prompt = f"""
Original Message:
{current_message}

{"Original Subject: " + current_subject if current_subject else ""}

Critique:
{state.get('critique', '')}

Message Type: {state['message_type']}
{limit_str}
Language: {state['language']}

Generate an improved version that addresses all critique points.
{"Output JSON with 'subject' and 'body' keys." if state['message_type'].startswith('email') else "Output only the message text."}
"""

    try:
        if state["message_type"].startswith("email"):
            response = await ai.generate_json(
                prompt=refine_prompt,
                system=refine_system,
                temperature=0.5,
            )
            return {
                "refined_message": response.get("body", current_message),
                "refined_subject": response.get("subject", current_subject),
                "iteration_count": state["iteration_count"] + 1,
            }
        else:
            response = await ai.generate(
                prompt=refine_prompt,
                system=refine_system,
                temperature=0.5,
                max_tokens=300,
            )
            return {
                "refined_message": response.strip(),
                "refined_subject": "",
                "iteration_count": state["iteration_count"] + 1,
            }
    except Exception as e:
        logger.error(f"Error refining: {e}")
        return {"iteration_count": state["iteration_count"] + 1}


async def validate_node(state: PersonalizationState) -> dict:
    """Validate message meets all quality criteria."""
    logger.info("Validating message quality")

    message = state.get("refined_message") or state.get("draft_message", "")
    subject = state.get("refined_subject") or state.get("draft_subject", "")
    message_type = state["message_type"]
    language = state["language"]

    validation_result = {
        "length_valid": False,
        "personalization_score": 0.0,
        "has_cta": False,
        "tone_appropriate": True,  # Assume true, could be AI-validated
    }

    # Validate length
    limits = LENGTH_LIMITS.get(message_type, {})
    if "max_chars" in limits:
        char_count = len(message)
        validation_result["length_valid"] = (
            limits.get("min_chars", 0) <= char_count <= limits["max_chars"]
        )
        validation_result["char_count"] = char_count
        validation_result["max_chars"] = limits["max_chars"]
    elif "max_words" in limits:
        word_count = len(message.split())
        validation_result["length_valid"] = (
            limits.get("min_words", 0) <= word_count <= limits["max_words"]
        )
        validation_result["word_count"] = word_count
        validation_result["max_words"] = limits["max_words"]

    # Calculate personalization score
    personalization_score = 0.0
    elements_found = []

    # Check for company name
    if state["prospect_company"].lower() in message.lower():
        personalization_score += 0.25
        elements_found.append("company_name")

    # Check for first name
    if state["prospect_name"].lower() in message.lower():
        personalization_score += 0.15
        elements_found.append("first_name")

    # Check for pain point references
    for pain_point in state.get("pain_points", []):
        keywords = pain_point.lower().split()[:3]
        if any(kw in message.lower() for kw in keywords if len(kw) > 3):
            personalization_score += 0.2
            elements_found.append("pain_point")
            break

    # Check for metrics/numbers
    import re
    if re.search(r"\d+%|\d+x|\$\d+|\d+\+", message):
        personalization_score += 0.2
        elements_found.append("metric")

    # Check for industry reference
    if state.get("industry", "").lower() in message.lower():
        personalization_score += 0.1
        elements_found.append("industry")

    # Check for role reference
    role_words = state.get("prospect_role", "").lower().split()
    if any(word in message.lower() for word in role_words if len(word) > 3):
        personalization_score += 0.1
        elements_found.append("role")

    validation_result["personalization_score"] = min(personalization_score, 1.0)
    validation_result["personalization_elements"] = elements_found

    # Check for CTA
    cta_patterns = [
        r"\bcall\b", r"\bchat\b", r"\bconnect\b", r"\bmeeting\b",
        r"\bschedule\b", r"\bbook\b", r"\?$", r"\binterested\b",
        r"\bopen to\b", r"\bwould you\b", r"\bworth\b",
        r"\bllamada\b", r"\bconectemos\b", r"\binteresa\b",  # Spanish
        r"\bligação\b", r"\bconectar\b", r"\binteresse\b",  # Portuguese
    ]
    validation_result["has_cta"] = any(
        re.search(p, message.lower()) for p in cta_patterns
    )

    # Determine if valid
    is_valid = (
        validation_result["length_valid"]
        and validation_result["personalization_score"] >= 0.4
        and validation_result["has_cta"]
    )

    return {
        "validation_result": validation_result,
        "is_valid": is_valid,
    }


async def format_output_node(state: PersonalizationState) -> dict:
    """Format the final message for output."""
    logger.info("Formatting final output")

    message = state.get("refined_message") or state.get("draft_message", "")
    subject = state.get("refined_subject") or state.get("draft_subject", "")

    # For LinkedIn connection requests, ensure under 200 chars
    if state["message_type"] == "connection_request":
        if len(message) > 200:
            # Truncate intelligently at sentence/word boundary
            message = message[:197].rsplit(" ", 1)[0] + "..."
            logger.warning("Truncated LinkedIn connection request to 200 chars")

    return {
        "final_message": message,
        "final_subject": subject,
    }


# =============================================================================
# Helper Functions
# =============================================================================


def _build_system_prompt(state: PersonalizationState) -> str:
    """Build the system prompt for message generation."""
    message_type = state["message_type"]
    icp = state["icp_type"]
    language = state["language"]

    pillar_config = PILLAR_MATRIX.get(icp, PILLAR_MATRIX["sme"])

    if message_type == "connection_request":
        return f"""You are an expert B2B outreach copywriter specializing in LinkedIn connection requests.
Generate messages under 200 characters that:
- Start with the prospect's first name or a personalized observation
- Reference something specific about their role or company
- Mention your value proposition briefly
- End with a connection invite ("Would love to connect!" or similar)

Tone: {pillar_config['tone']}
Language: {language.upper()}

CRITICAL: Message MUST be under 200 characters. This is a hard limit."""

    elif message_type == "linkedin_message":
        return f"""You are an expert B2B outreach copywriter for LinkedIn messages.
Generate messages that:
- Open with value or insight (not "I hope this finds you well")
- Reference a specific pain point or challenge they face
- Present a clear value proposition
- Include social proof if relevant
- End with a soft CTA (suggest a call, not demand one)

Tone: {pillar_config['tone']}
Language: {language.upper()}
Keep under 500 characters."""

    elif message_type.startswith("email"):
        sequence_context = ""
        if message_type == "email_initial":
            sequence_context = "This is the initial cold email. Be direct and value-focused."
        elif message_type == "email_followup_1":
            sequence_context = "This is follow-up #1 (Day 1). Add value, share a useful insight."
        elif message_type == "email_followup_2":
            sequence_context = "This is follow-up #2 (Day 4). Include social proof or case study."
        elif message_type == "email_followup_3":
            sequence_context = "This is follow-up #3 (Day 8). Keep it short, ask if timing is off."
        elif message_type == "email_followup_4":
            sequence_context = "This is the break-up email (Day 14). Offer to close the loop."

        return f"""You are an expert B2B email copywriter.
Generate emails that:
- Have compelling subject lines (under 60 chars, specific to them)
- Lead with a relevant observation about their company
- Present ONE clear pain point you can solve
- Include a specific metric or proof point
- End with a soft CTA (15-minute call, not a hard sell)

{sequence_context}

Tone: {pillar_config['tone']}
Language: {language.upper()}

Output as JSON with 'subject' and 'body' keys."""

    return "You are an expert B2B copywriter."


def _build_user_prompt(state: PersonalizationState) -> str:
    """Build the user prompt for message generation."""
    message_type = state["message_type"]

    prompt = f"""Generate a personalized {message_type.replace('_', ' ')} for:

PROSPECT:
- Name: {state['prospect_name']} ({state['prospect_full_name']})
- Title: {state['prospect_role']}
- Company: {state['prospect_company']}
- Industry: {state.get('industry', 'N/A')}

PERSONALIZATION CONTEXT:
- Pain Points: {', '.join(state.get('pain_points', [])) or 'N/A'}
- Key Metrics: {', '.join(state.get('key_metrics', [])) or 'N/A'}
- Value Proposition: {state.get('value_proposition', 'N/A')}
"""

    if state.get("talking_points"):
        prompt += f"\nOPENING HOOKS (use one if relevant):\n"
        for i, point in enumerate(state["talking_points"][:3], 1):
            prompt += f"{i}. {point}\n"

    if state.get("competitive_angle"):
        prompt += f"\nCOMPETITIVE ANGLE:\n{state['competitive_angle']}\n"

    prompt += f"""
MESSAGING PILLAR: {state.get('messaging_pillar', 'roi_results')}
KEY MESSAGE: {state.get('pillar_key_message', '')}
LANGUAGE: {state['language']}

OUR SERVICE: AI Whisperers - AI training and automation for professionals

Generate the message now. Be specific and personalized - avoid generic phrases."""

    return prompt


# =============================================================================
# Graph Construction
# =============================================================================


def create_personalization_graph():
    """Create the Personalization Agent graph."""
    workflow = StateGraph(PersonalizationState)

    # Add nodes
    workflow.add_node("extract_context", extract_context_node)
    workflow.add_node("select_pillar", select_pillar_node)
    workflow.add_node("generate_draft", generate_draft_node)
    workflow.add_node("critique", critique_node)
    workflow.add_node("refine", refine_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("format_output", format_output_node)

    # Define edges
    workflow.set_entry_point("extract_context")
    workflow.add_edge("extract_context", "select_pillar")
    workflow.add_edge("select_pillar", "generate_draft")
    workflow.add_edge("generate_draft", "critique")

    # Conditional: Should we refine or validate?
    def should_refine(state: PersonalizationState):
        if state["iteration_count"] < state["max_iterations"]:
            return "refine"
        return "validate"

    workflow.add_conditional_edges(
        "critique",
        should_refine,
        {"refine": "refine", "validate": "validate"},
    )

    workflow.add_edge("refine", "critique")  # Loop back for another critique

    # Conditional: Is message valid or should we try again?
    def check_validity(state: PersonalizationState):
        if state.get("is_valid", False):
            return "format_output"
        elif state["iteration_count"] < state["max_iterations"]:
            return "refine"
        return "format_output"  # Best effort output

    workflow.add_conditional_edges(
        "validate",
        check_validity,
        {"format_output": "format_output", "refine": "refine"},
    )

    workflow.add_edge("format_output", END)

    return workflow.compile()


# =============================================================================
# Agent Execution
# =============================================================================


async def generate_personalized_message(
    brand_brief: dict,
    prospect_name: str,
    prospect_full_name: str,
    prospect_role: str,
    prospect_company: str,
    message_type: MessageTypeType,
    icp_type: ICPType = "sme",
    industry: str = "",
    language: LanguageType = "en",
    max_iterations: int = 2,
) -> dict:
    """
    Generate a personalized outreach message.

    Args:
        brand_brief: Parsed brand brief dictionary
        prospect_name: First name of the prospect
        prospect_full_name: Full name of the prospect
        prospect_role: Job title/role
        prospect_company: Company name
        message_type: Type of message to generate
        icp_type: ICP classification (solopreneur/sme/enterprise)
        industry: Industry category
        language: Target language (en/es/pt)
        max_iterations: Max refinement iterations

    Returns:
        {
            "message": str,
            "subject": str (for emails),
            "validation": dict,
            "personalization_elements": list,
            "iterations": int
        }
    """
    logger.info(
        f"Generating {message_type} for {prospect_name} at {prospect_company}"
    )

    # Get length limit
    limits = LENGTH_LIMITS.get(message_type, {})
    max_length = limits.get("max_chars") or limits.get("max_words", 500)

    # Initialize state
    initial_state: PersonalizationState = {
        "brand_brief": brand_brief,
        "prospect_name": prospect_name,
        "prospect_full_name": prospect_full_name,
        "prospect_role": prospect_role,
        "prospect_company": prospect_company,
        "icp_type": icp_type,
        "industry": industry,
        "language": language,
        "message_type": message_type,
        "max_length": max_length,
        "pain_points": [],
        "key_metrics": [],
        "value_proposition": "",
        "competitive_angle": "",
        "talking_points": [],
        "messaging_pillar": "",
        "pillar_key_message": "",
        "draft_message": "",
        "draft_subject": "",
        "critique": "",
        "refined_message": "",
        "refined_subject": "",
        "validation_result": {},
        "is_valid": False,
        "final_message": "",
        "final_subject": "",
        "iteration_count": 0,
        "max_iterations": max_iterations,
        "errors": [],
    }

    # Create and run graph
    graph = create_personalization_graph()
    result = await graph.ainvoke(initial_state)

    return {
        "message": result.get("final_message", ""),
        "subject": result.get("final_subject", ""),
        "validation": result.get("validation_result", {}),
        "personalization_elements": result.get("validation_result", {}).get(
            "personalization_elements", []
        ),
        "iterations": result.get("iteration_count", 0),
        "is_valid": result.get("is_valid", False),
        "errors": result.get("errors", []),
    }
