"""
Campaign Generation Graph (v2)
==============================

Implements a sophisticated agentic workflow for campaign generation using LangGraph.
Nodes:
- Research: Parallel research on different aspects
- Synthesis: Combine research into insights
- Ideation: Generate initial concepts
- Critic: Review and critique ideas
- Refinement: Improve ideas based on critique
"""

import asyncio
import operator
from typing import Annotated, TypedDict, List, Dict, Any

from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ..services.ai_client import get_ai_manager
from ..services.research_service import get_research_service
from ..services.gpt_research_service import get_gpt_research_service
from ..services.file_operations import get_file_service
from ..logging_config import get_logger

logger = get_logger("campaign_graph")


# =============================================================================
# State Definition
# =============================================================================


class CampaignState(TypedDict):
    """State for the campaign generation graph."""

    project_id: str
    brand_name: str
    country: str
    num_ideas: int

    # Research
    research_topics: List[str]
    research_results: Annotated[List[str], operator.add]
    research_summary: str

    # Ideation
    concepts: List[Dict[str, Any]]

    # Refinement
    critiques: List[str]
    scored_ideas: List[Dict[str, Any]]

    # Meta
    messages: Annotated[List[BaseMessage], operator.add]
    errors: List[str]


# Import campaign memory (lazy load to avoid circular imports)
def get_campaign_memory_lazy():
    from ..services.campaign_memory import get_campaign_memory

    return get_campaign_memory()


# =============================================================================
# Nodes
# =============================================================================


async def research_node(state: CampaignState):
    """
    Conduct research using GPT Researcher.
    """
    project_id = state["project_id"]
    brand_name = state.get(
        "brand_name", "the brand"
    )  # Fallback if not in state, though it should be

    # Initialize services
    research_service = get_research_service()
    gpt_researcher = get_gpt_research_service()

    # Check if we already have research
    existing_research = await research_service.get_all_research(project_id)

    if (
        existing_research
        and len(existing_research) > 500
        and "Research failed" not in existing_research
    ):
        logger.info("Found valid existing research. Skipping new research.")
        return {
            "research_results": [existing_research],
            "messages": [SystemMessage(content="Using existing research.")],
        }

    if existing_research:
        logger.info(
            "Existing research found but appears invalid or incomplete. Re-running research."
        )

    # If no research, conduct new research
    logger.info(f"Conducting deep research for {brand_name}")
    try:
        # Enhanced research query
        query = (
            f"Deep dive marketing research for {brand_name} in Paraguay. "
            "Focus on: 1. Current market trends and cultural context. "
            "2. Detailed competitor analysis (direct and indirect). "
            "3. Target audience psychographics and behaviors. "
            "4. Recent successful campaigns in the category."
        )

        report = await gpt_researcher.conduct_research(query=query, report_type="research_report")

        # Save research to file
        try:
            file_service = get_file_service()
            await file_service.save_research_file(
                project_id=project_id,
                category="01-mercado-general",
                filename="initial-research",
                content=report,
            )
            logger.info("Saved research report to 01-mercado-general/initial-research.md")
        except Exception as e:
            logger.warning(f"Failed to save research file: {e}")

        return {
            "research_results": [report],
            "messages": [SystemMessage(content="Conducted deep research using GPT Researcher.")],
        }
    except Exception as e:
        logger.error(f"Research failed: {e}")
        return {
            "research_results": [f"Research failed: {e}. Using basic knowledge."],
            "errors": [str(e)],
        }


async def synthesis_node(state: CampaignState):
    """Synthesize research into key insights."""
    logger.info("Synthesizing research...")
    ai = get_ai_manager()

    research_results = state.get("research_results", [])
    research_text = "\n\n".join(research_results)

    # Enhanced synthesis prompt
    prompt = f"""
    You are a Strategic Planner. Analyze the following research to build a solid foundation for a creative campaign.
    
    RESEARCH DATA:
    {research_text[:15000]}
    
    Provide a structured synthesis in the following format:
    
    1. MARKET CONTEXT: Key trends and cultural shifts in Paraguay relevant to the brand.
    2. COMPETITOR LANDSCAPE: What are competitors doing? Where is the white space?
    3. AUDIENCE DEEP DIVE: Psychographics, pain points, and desires.
    4. STRATEGIC TERRITORIES: 3 potential angles or themes for the campaign.
    
    Keep it actionable and inspiring for a creative team.
    """

    summary = await ai.generate(prompt, temperature=0.4)

    return {"research_summary": summary}


async def ideation_node(state: CampaignState):
    """Generate campaign concepts using two-phase approach for Ollama compatibility."""
    logger.info("Generating concepts (two-phase approach)...")
    ai = get_ai_manager()

    num_ideas = state.get("num_ideas", 5)
    summary = state["research_summary"]

    # PHASE 1: Generate Base Concepts (6 fields)
    logger.info(f"Phase 1: Generating {num_ideas} base concepts...")

    phase1_system = "You are a Creative Director. Return ONLY a JSON array."
    phase1_user = f"""Based on: {summary[:3000]}

Generate {num_ideas} campaign concepts for Gen Z Paraguay.
Return JSON array with: title, description, rationale, target_audience, channels, kpis.

Example: [{{"title": "...", "description": "...", "rationale": "...", "target_audience": "...", "channels": [...], "kpis": [...]}}]
"""

    try:
        # Phase 1 - Force OpenAI for reliable JSON generation
        phase1_response = await ai.generate_json(
            phase1_user,
            system=phase1_system,
            temperature=0.8,
            use_fallback=True,  # Force OpenAI for structured output
        )

        if isinstance(phase1_response, list):
            base_concepts = phase1_response
        elif isinstance(phase1_response, dict):
            base_concepts = phase1_response.get("ideas", phase1_response.get("concepts", []))
        else:
            base_concepts = []

        logger.info(f"Phase 1: {len(base_concepts)} concepts generated")

        if not base_concepts:
            return {"concepts": [], "errors": ["No concepts in Phase 1"]}

        # PHASE 2: Enrich Each Concept
        logger.info(f"Phase 2: Enriching {len(base_concepts)} concepts...")

        enriched_concepts = []
        for i, concept in enumerate(base_concepts):
            logger.info(f"Enriching {i+1}/{len(base_concepts)}: {concept.get('title', 'Untitled')}")

            phase2_user = f"""Campaign: "{concept.get('title', '')}"
Description: {concept.get('description', '')}

Add as JSON: budget_tier (Low/Medium/High), timeline (1-3/3-6/6+ months), key_message, call_to_action, sustainability_component, risks (array), success_factors (array).
"""

            try:
                phase2_response = await ai.generate_json(
                    phase2_user, system="Strategic planner. Return JSON.", temperature=0.6
                )

                if isinstance(phase2_response, dict):
                    concept.update(phase2_response)
                else:
                    # Defaults
                    concept.setdefault("budget_tier", "Medium")
                    concept.setdefault("timeline", "3-6 months")
                    concept.setdefault("key_message", "TBD")
                    concept.setdefault("call_to_action", "TBD")
                    concept.setdefault("sustainability_component", "TBD")
                    concept.setdefault("risks", ["TBD"])
                    concept.setdefault("success_factors", ["TBD"])

            except Exception as e:
                logger.error(f"Phase 2 failed for {concept.get('title')}: {e}")
                # Add defaults
                concept.setdefault("budget_tier", "Medium")
                concept.setdefault("timeline", "3-6 months")
                concept.setdefault("key_message", "TBD")
                concept.setdefault("call_to_action", "TBD")
                concept.setdefault("sustainability_component", "TBD")
                concept.setdefault("risks", ["TBD"])
                concept.setdefault("success_factors", ["TBD"])

            enriched_concepts.append(concept)

        logger.info(f"Two-phase complete: {len(enriched_concepts)} enriched concepts")
        return {"concepts": enriched_concepts}

    except Exception as e:
        logger.error(f"Ideation failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {"errors": [str(e)]}


async def critic_node(state: CampaignState):
    """Critique and score the generated concepts."""
    logger.info("Critiquing concepts...")
    ai = get_ai_manager()

    concepts = state["concepts"]
    critiques = []
    scored_ideas = []

    for concept in concepts:
        prompt = f"""
        Critique this campaign idea:
        Title: {concept.get('title')}
        Description: {concept.get('description')}
        
        Provide:
        1. A critique (strengths/weaknesses)
        2. A score from 0-10 for: relevance, creativity, feasibility, impact.
        
        Return JSON.
        """

        try:
            response = await ai.generate_json(prompt, temperature=0.2)

            # Handle both list and dict responses
            if isinstance(response, list):
                response = response[0] if response else {}

            critique_text = (
                response.get("critique", "No critique")
                if isinstance(response, dict)
                else "No critique"
            )
            critiques.append(critique_text)

            # Enrich concept with scores
            concept["scores"] = response.get("scores", {}) if isinstance(response, dict) else {}
            concept["critique"] = critique_text

            # Calculate overall
            scores = concept["scores"]
            if scores:
                avg = sum(scores.values()) / len(scores)
                concept["overall_score"] = avg

            scored_ideas.append(concept)

        except Exception as e:
            logger.error(f"Critique failed for {concept.get('title')}: {e}")

    # Store high-quality campaigns in RAG memory for future reference
    try:
        memory = get_campaign_memory_lazy()
        stored_count = 0

        for idea in scored_ideas:
            # Only store good campaigns (score >= 7.0)
            if idea.get("overall_score", 0) >= 7.0:
                await memory.store_campaign(
                    project_id=state["project_id"],
                    idea_id=str(scored_ideas.index(idea)),
                    title=idea.get("title", ""),
                    concept=idea.get("description", ""),
                    rationale=idea.get("rationale", ""),
                    execution=[],  # This version doesn't have execution plans
                    score=idea["overall_score"],
                    client="",  # Would need to be added to state
                    country="",  # Would need to be added to state
                )
                stored_count += 1

        if stored_count > 0:
            logger.info(f"[RAG] Stored {stored_count} high-quality campaigns for future reference")
    except Exception as e:
        logger.warning(f"[RAG] Could not store campaigns: {e}")

    return {"critiques": critiques, "scored_ideas": scored_ideas}


async def refinement_node(state: CampaignState):
    """Refine ideas based on critique (Optional/Future)."""
    # For now, just pass through.
    # In full v2, this would loop back or improve the best ideas.
    return {}


# =============================================================================
# Graph Construction
# =============================================================================


def get_campaign_graph():
    """Build and return the compiled graph."""
    workflow = StateGraph(CampaignState)

    # Add nodes
    workflow.add_node("research", research_node)
    workflow.add_node("synthesis", synthesis_node)
    workflow.add_node("ideation", ideation_node)
    workflow.add_node("critic", critic_node)

    # Define edges
    workflow.set_entry_point("research")
    workflow.add_edge("research", "synthesis")
    workflow.add_edge("synthesis", "ideation")
    workflow.add_edge("ideation", "critic")
    workflow.add_edge("critic", END)

    return workflow.compile()


# =============================================================================
# Runner Wrapper
# =============================================================================


class CampaignGraphRunner:
    """Wrapper to run the graph easily."""

    def __init__(self):
        self.graph = get_campaign_graph()

    async def run_campaign(self, project_id: str, num_ideas: int = 5) -> Dict[str, Any]:
        """Run the full campaign generation workflow."""
        # Fetch project metadata to get brand context
        try:
            file_service = get_file_service()
            metadata = file_service.get_project_metadata(project_id)
            brand_name = metadata.get("client", "the brand")
            country = metadata.get("country", "Paraguay")
        except Exception as e:
            logger.warning(f"Could not fetch project metadata: {e}")
            brand_name = "the brand"
            country = "Paraguay"

        initial_state = CampaignState(
            project_id=project_id,
            brand_name=brand_name,
            country=country,
            num_ideas=num_ideas,
            research_topics=[],
            research_results=[],
            research_summary="",
            concepts=[],
            critiques=[],
            scored_ideas=[],
            messages=[],
            errors=[],
        )

        final_state = await self.graph.ainvoke(initial_state)
        return final_state
