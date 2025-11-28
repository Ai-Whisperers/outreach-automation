"""
Research Agent using LangGraph.

This agent orchestrates the research process by dynamically planning queries,
executing searches, and analyzing results until sufficient information is gathered.
"""

import operator
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from ..config import get_settings
from ..logging_config import get_logger
from ..services.web_fetcher import get_web_fetcher
from ..services.web_search import get_web_search_service

logger = get_logger("research_agent")
settings = get_settings()

# =============================================================================
# State Definition
# =============================================================================

class ResearchState(TypedDict):
    """State for the research agent."""
    project_id: str
    topic: str
    subtopics: list[str]
    # Messages history
    messages: Annotated[list[BaseMessage], operator.add]
    # Research findings
    findings: Annotated[list[str], operator.add]
    # Search queries to execute
    pending_queries: list[str]
    # Iteration count
    iterations: int
    # Is research complete?
    is_complete: bool


# =============================================================================
# Nodes
# =============================================================================

async def generate_queries(state: ResearchState):
    """Generate search queries based on current state."""
    logger.info(f"Generating queries for topic: {state['topic']}")

    # Initialize LLM
    llm = _get_llm()

    # Context from previous findings
    context = "\n".join(state.get("findings", []))

    prompt = f"""You are a Research Agent planning the next step of research.
    
    Topic: {state['topic']}
    Subtopics to cover: {', '.join(state['subtopics'])}
    
    Current Findings:
    {context if context else "No findings yet."}
    
    Generate 3 specific search queries to gather missing information.
    Return ONLY the queries, one per line.
    """

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    queries = [q.strip() for q in response.content.split('\n') if q.strip()]

    return {
        "pending_queries": queries,
        "iterations": state["iterations"] + 1
    }


async def execute_search(state: ResearchState):
    """Execute pending search queries."""
    queries = state.get("pending_queries", [])
    if not queries:
        return {"pending_queries": []}

    logger.info(f"Executing {len(queries)} searches")
    search_service = get_web_search_service()
    fetch_service = get_web_fetcher()

    new_findings = []

    for query in queries:
        # Search
        results = await search_service.search(query, num_results=2)
        urls = [r["url"] for r in results]

        # Fetch content
        contents = await fetch_service.fetch_multiple(urls)

        for content in contents:
            if content.get("content"):
                summary = content["content"][:500] + "..." # Truncate for now
                new_findings.append(f"Source: {content['url']}\nContent: {summary}")

    return {
        "findings": new_findings,
        "pending_queries": [] # Clear executed queries
    }


async def analyze_results(state: ResearchState):
    """Analyze findings and check if we have enough info."""
    logger.info("Analyzing research results")

    llm = _get_llm()

    context = "\n".join(state["findings"])

    prompt = f"""Analyze the research findings for the topic: {state['topic']}
    
    Findings:
    {context}
    
    Do we have sufficient information to cover these subtopics?
    {', '.join(state['subtopics'])}
    
    Reply with 'YES' if sufficient, or 'NO' if more research is needed.
    """

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    decision = response.content.strip().upper()

    is_complete = "YES" in decision or state["iterations"] >= 3

    return {"is_complete": is_complete}


# =============================================================================
# Graph Construction
# =============================================================================

def create_research_graph():
    """Create the LangGraph workflow."""
    workflow = StateGraph(ResearchState)

    # Add nodes
    workflow.add_node("generate_queries", generate_queries)
    workflow.add_node("execute_search", execute_search)
    workflow.add_node("analyze_results", analyze_results)

    # Define edges
    workflow.set_entry_point("generate_queries")

    workflow.add_edge("generate_queries", "execute_search")
    workflow.add_edge("execute_search", "analyze_results")

    # Conditional edge
    def check_completion(state):
        if state["is_complete"]:
            return "end"
        return "continue"

    workflow.add_conditional_edges(
        "analyze_results",
        check_completion,
        {
            "end": END,
            "continue": "generate_queries"
        }
    )

    return workflow.compile()


# =============================================================================
# Helpers
# =============================================================================

def _get_llm():
    """Get the configured LLM."""
    if settings.anthropic_api_key:
        return ChatAnthropic(
            model="claude-3-sonnet-20240229",
            anthropic_api_key=settings.anthropic_api_key
        )
    else:
        return ChatOpenAI(
            model="gpt-4-turbo-preview",
            api_key=settings.openai_api_key
        )
