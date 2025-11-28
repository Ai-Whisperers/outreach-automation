"""
Ideation Agent

A LangGraph-based agent for generating, critiquing, and refining campaign ideas.
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph

from ..logging_config import get_logger
from ..models import Idea
from ..services.ai_client import get_ai_manager, get_prompt_loader

logger = get_logger("ideation_agent")

# =============================================================================
# State Definition
# =============================================================================

class IdeationState(TypedDict):
    """State for the Ideation Agent."""
    project_id: str
    brief_text: str
    research_summary: str
    ideas: list[Idea]
    critique: str
    iteration_count: int
    max_iterations: int

# =============================================================================
# Nodes
# =============================================================================

async def brainstorm_node(state: IdeationState) -> dict:
    """Generate initial ideas based on brief and research."""
    logger.info("Node: Brainstorming ideas")

    ai = get_ai_manager()
    prompts = get_prompt_loader()

    # Format prompt
    system, user = prompts.format(
        "ideation", "brainstorm",
        brief_challenge=state["brief_text"], # Passing full text
        target_audience="See brief", # Included in brief text
        research_summary=state["research_summary"]
    )

    # Generate ideas (using JSON mode for structure)
    response = await ai.generate_json(
        prompt=user,
        system=system,
        temperature=0.8
    )

    # Parse into Idea objects
    new_ideas = []
    for i, item in enumerate(response.get("ideas", [])):
        new_ideas.append(Idea(
            title=item.get("title", f"Idea {i+1}"),
            description=item.get("description", ""),
            rationale=item.get("rationale", ""),
            score=0.0 # Initial score
        ))

    return {"ideas": new_ideas, "iteration_count": 0}

async def critique_node(state: IdeationState) -> dict:
    """Critique the current batch of ideas."""
    logger.info("Node: Critiquing ideas")

    ai = get_ai_manager()
    prompts = get_prompt_loader()

    # Format ideas for critique
    ideas_text = "\n\n".join([
        f"Idea {i+1}: {idea.title}\n{idea.description}\nRationale: {idea.rationale}"
        for i, idea in enumerate(state["ideas"])
    ])

    system, user = prompts.format(
        "ideation", "critique",
        brief_challenge=state["brief_text"],
        target_audience="See brief",
        ideas_text=ideas_text
    )

    critique = await ai.generate(
        prompt=user,
        system=system,
        temperature=0.4
    )

    return {"critique": critique}

async def refine_node(state: IdeationState) -> dict:
    """Refine ideas based on critique."""
    logger.info("Node: Refining ideas")

    ai = get_ai_manager()
    prompts = get_prompt_loader()

    # Format ideas for refinement
    ideas_text = "\n\n".join([
        f"Idea {i+1}: {idea.title}\n{idea.description}\nRationale: {idea.rationale}"
        for i, idea in enumerate(state["ideas"])
    ])

    system, user = prompts.format(
        "ideation", "refine",
        brief_challenge=state["brief_text"],
        ideas_text=ideas_text,
        critique=state["critique"]
    )

    response = await ai.generate_json(
        prompt=user,
        system=system,
        temperature=0.7
    )

    # Parse refined ideas
    refined_ideas = []
    for i, item in enumerate(response.get("ideas", [])):
        refined_ideas.append(Idea(
            title=item.get("title", f"Refined Idea {i+1}"),
            description=item.get("description", ""),
            rationale=item.get("rationale", ""),
            score=0.0
        ))

    return {
        "ideas": refined_ideas,
        "iteration_count": state["iteration_count"] + 1
    }

async def select_node(state: IdeationState) -> dict:
    """Select and finalize the best ideas."""
    logger.info("Node: Selecting best ideas")
    # For now, we just pass through the refined ideas.
    # In a more complex version, this could filter or rank them.
    return {}

# =============================================================================
# Graph Construction
# =============================================================================

def create_ideation_graph():
    """Create the Ideation Agent graph."""
    workflow = StateGraph(IdeationState)

    # Add nodes
    workflow.add_node("brainstorm", brainstorm_node)
    workflow.add_node("critique", critique_node)
    workflow.add_node("refine", refine_node)
    workflow.add_node("select", select_node)

    # Define edges
    workflow.set_entry_point("brainstorm")
    workflow.add_edge("brainstorm", "critique")

    # Conditional edge for iteration
    def should_continue(state: IdeationState):
        if state["iteration_count"] < state["max_iterations"]:
            return "refine"
        return "select"

    workflow.add_conditional_edges(
        "critique",
        should_continue,
        {
            "refine": "refine",
            "select": "select"
        }
    )

    workflow.add_edge("refine", "critique") # Loop back to critique
    workflow.add_edge("select", END)

    return workflow.compile()
