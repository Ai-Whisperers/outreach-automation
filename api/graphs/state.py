"""
State models for LangGraph workflows.
"""

import operator
from datetime import datetime
from typing import Annotated, TypedDict


class CampaignState(TypedDict):
    """
    State for campaign generation workflow.

    This state is passed between all nodes in the graph and tracks
    the complete campaign generation process.
    """

    # ========================================================================
    # Project Information
    # ========================================================================
    project_id: str
    """Unique project identifier"""

    brief: str
    """Campaign brief text"""

    client: str
    """Client name (e.g., 'Ueno Bank')"""

    country: str
    """Target country (e.g., 'Paraguay')"""

    # ========================================================================
    # Research Phase (Parallel Execution)
    # ========================================================================
    market_research: str
    """Market trends and competitive analysis"""

    cultural_insights: str
    """Cultural context and local insights"""

    digital_trends: str
    """Digital behavior and social media trends"""

    research_complete: bool
    """Flag indicating all research is done"""

    # ========================================================================
    # Ideation Phase
    # ========================================================================
    ideas: Annotated[list[dict], operator.add]
    """
    List of generated ideas (append-only for LangGraph).
    Each idea is a dict with: title, headline, description, rationale, execution
    """

    current_batch: int
    """Current batch number (for progress tracking)"""

    total_batches: int
    """Total number of batches to generate"""

    # ========================================================================
    # Evaluation Phase
    # ========================================================================
    scored_ideas: list[dict]
    """Ideas with scores attached"""

    # ========================================================================
    # Metadata & Monitoring
    # ========================================================================
    execution_start_time: datetime
    """When workflow started"""

    execution_end_time: datetime | None
    """When workflow completed"""

    errors: Annotated[list[str], operator.add]
    """List of errors encountered (append-only)"""

    current_node: str
    """Name of currently executing node (for debugging)"""
