"""
API Routes Package
"""

from .analytics import router as analytics_router
from .brief import router as brief_router
from .export import router as export_router
from .ideas import router as ideas_router
from .iteration import router as iteration_router
from .projects import router as projects_router
from .research import router as research_router

# Outreach routes
from .campaigns import router as campaigns_router
from .prospects import router as prospects_router
from .messages import router as messages_router
from .outreach import router as outreach_router

# New routes for enhanced email system
from .webhooks import router as webhooks_router
from .sequences import router as sequences_router
from .deliverability import router as deliverability_router
from .scraper_import import router as scraper_import_router

__all__ = [
    "projects_router",
    "brief_router",
    "research_router",
    "ideas_router",
    "export_router",
    "iteration_router",
    "analytics_router",
    # Outreach
    "campaigns_router",
    "prospects_router",
    "messages_router",
    "outreach_router",
    # Enhanced email system
    "webhooks_router",
    "sequences_router",
    "deliverability_router",
    "scraper_import_router",
]
