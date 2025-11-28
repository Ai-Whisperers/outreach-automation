"""
Analytics API Routes.

Endpoints for generating analytics reports and insights.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import APIKeyDep, get_analytics_service
from ..logging_config import get_logger
from ..services.analytics_service import AnalyticsService

logger = get_logger("routes.analytics")

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post("/projects/{project_id}/research-intelligence")
async def generate_research_intelligence(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: APIKeyDep = None
) -> dict[str, Any]:
    """
    Generate Research Intelligence Report.

    Analyzes all research files to extract:
    - Market landscape overview
    - Consumer insights
    - Cultural context
    - Opportunity mapping

    Returns:
        Report metadata and file path
    """
    try:
        result = await analytics.generate_research_intelligence(project_id)
        return result
    except Exception as e:
        logger.error(f"Failed to generate research intelligence: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/strategic-synthesis")
async def synthesize_strategic_insights(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: str = Depends(APIKeyDep)
) -> dict[str, Any]:
    """
    Generate Strategic Insights Synthesis.

    Creates executive summary:
    - The big picture (3 bullets)
    - Key insights (top 5)
    - Strategic territories
    - Success factors

    Returns:
        Synthesis metadata and file path
    """
    try:
        result = await analytics.synthesize_strategic_insights(project_id)
        return result
    except Exception as e:
        logger.error(f"Failed to synthesize strategic insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/insights-mapping")
async def map_insights_to_ideas(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: str = Depends(APIKeyDep)
) -> dict[str, Any]:
    """
    Create Insights-to-Ideas Mapping.

    Shows:
    - Which insight inspired each idea
    - Insight coverage analysis
    - Insight strength ranking

    Returns:
        Mapping metadata and file path
    """
    try:
        result = await analytics.map_insights_to_ideas(project_id)
        return result
    except Exception as e:
        logger.error(f"Failed to map insights to ideas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/generate-all-analytics")
async def generate_all_analytics(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: str = Depends(APIKeyDep)
) -> dict[str, Any]:
    """
    Generate all Phase 1 analytics reports.

    Convenience endpoint that generates:
    1. Research Intelligence Report
    2. Strategic Insights Synthesis
    3. Insights-to-Ideas Mapping

    Returns:
        Combined results from all reports
    """
    try:
        logger.info(f"Generating all analytics for project: {project_id}")

        results = {}

        # Generate research intelligence
        results["research_intelligence"] = await analytics.generate_research_intelligence(project_id)

        # Generate strategic synthesis
        results["strategic_synthesis"] = await analytics.synthesize_strategic_insights(project_id)

        # Generate insights mapping (only if ideas exist)
        mapping_result = await analytics.map_insights_to_ideas(project_id)
        if mapping_result["status"] != "no_ideas":
            results["insights_mapping"] = mapping_result

        return {
            "status": "success",
            "reports_generated": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Failed to generate all analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/competitive-intelligence")
async def analyze_competitors(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: str = Depends(APIKeyDep)
) -> dict[str, Any]:
    """
    Generate Competitive Intelligence Dashboard.

    Analyzes competitor data to create:
    - Competitor landscape map
    - Campaign analysis
    - Strengths & weaknesses
    - Strategic recommendations

    Returns:
        Competitive analysis metadata and file path
    """
    try:
        result = await analytics.analyze_competitors(project_id)
        return result
    except Exception as e:
        logger.error(f"Failed to analyze competitors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/trend-analysis")
async def identify_trends(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: str = Depends(APIKeyDep)
) -> dict[str, Any]:
    """
    Generate Trend Analysis Report.

    Identifies and analyzes trends:
    - Macro trends (society-level)
    - Industry trends (category evolution)
    - Micro trends (emerging behaviors)
    - Trend implications for brand

    Returns:
        Trend analysis metadata and file path
    """
    try:
        result = await analytics.identify_trends(project_id)
        return result
    except Exception as e:
        logger.error(f"Failed to identify trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/research-quality")
async def assess_research_quality(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: str = Depends(APIKeyDep)
) -> dict[str, Any]:
    """
    Generate Research Quality Dashboard.

    Assesses research completeness and quality:
    - Coverage analysis by category
    - Source quality ratings
    - Gap identification
    - Recommendations for improvement

    Returns:
        Quality assessment metadata and file path
    """
    try:
        result = await analytics.assess_research_quality(project_id)
        return result
    except Exception as e:
        logger.error(f"Failed to assess research quality: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/audience-personas")
async def create_audience_personas(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: str = Depends(APIKeyDep)
) -> dict[str, Any]:
    """Generate Audience Deep Dive Report with detailed personas."""
    try:
        result = await analytics.create_audience_personas(project_id)
        return result
    except Exception as e:
        logger.error(f"Failed to create audience personas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/content-strategy")
async def generate_content_strategy(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: str = Depends(APIKeyDep)
) -> dict[str, Any]:
    """Generate Content Strategy Framework."""
    try:
        result = await analytics.generate_content_strategy(project_id)
        return result
    except Exception as e:
        logger.error(f"Failed to generate content strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/cultural-sensitivity")
async def validate_cultural_sensitivity(
    project_id: str,
    analytics: AnalyticsService = Depends(get_analytics_service),
    _: str = Depends(APIKeyDep)
) -> dict[str, Any]:
    """Generate Cultural Sensitivity Analysis."""
    try:
        result = await analytics.validate_cultural_sensitivity(project_id)
        return result
    except Exception as e:
        logger.error(f"Failed to validate cultural sensitivity: {e}")
        raise HTTPException(status_code=500, detail=str(e))
