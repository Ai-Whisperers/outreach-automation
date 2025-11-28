"""
Main FastAPI Application

Entry point for the MAGA (Marketing AI Generation Assistant) API.
"""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_project_config, get_settings
from .exceptions import CampaignGeneratorError
from .logging_config import get_logger, setup_logging
from .routes import (
    analytics_router,
    brief_router,
    export_router,
    ideas_router,
    iteration_router,
    projects_router,
    research_router,
    # Outreach routers
    campaigns_router,
    prospects_router,
    messages_router,
    outreach_router,
    # Enhanced email system routers
    webhooks_router,
    sequences_router,
    deliverability_router,
    scraper_import_router,
)
from .security import RateLimitMiddleware, RequestIDMiddleware, SecurityHeadersMiddleware
from .services.cache import get_ai_cache

# Initialize logging
settings = get_settings()
setup_logging(
    level=settings.log_level,
    environment=settings.environment
)
logger = get_logger("main")


# =============================================================================
# Application Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting Campaign Generator API")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Projects directory: {settings.projects_dir}")

    # Verify configuration (optional - don't fail startup if config is missing)
    try:
        config = get_project_config()
        if hasattr(config, 'scoring_criteria'):
            logger.info(f"Loaded {len(config.scoring_criteria)} scoring criteria")
        if hasattr(config, 'ai_primary') and hasattr(config, 'ai_model'):
            logger.info(f"AI Provider: {config.ai_primary} ({config.ai_model})")
    except Exception as e:
        logger.warning(f"Could not load project configuration: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Campaign Generator API")


# =============================================================================
# Application Setup
# =============================================================================

app = FastAPI(
    title="Campaign Generator API",
    description="API for generating marketing campaign research and creative ideas",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Security middleware (order matters - first added = last executed)
# RequestIDMiddleware should be first so it runs before other middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)

# CORS middleware - use configured origins
allowed_origins = [
    origin.strip()
    for origin in settings.allowed_origins.split(",")
    if origin.strip()
]

# In development, allow all origins
if settings.debug:
    allowed_origins = ["*"]
    logger.warning("Debug mode: CORS allows all origins")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True if allowed_origins != ["*"] else False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

logger.info(f"CORS configured for origins: {allowed_origins}")
logger.info(f"Rate limiting: {'enabled' if settings.rate_limit_enabled else 'disabled'}")
logger.info(f"API key auth: {'enabled' if settings.api_key else 'disabled (development)'}")

# Include routers
app.include_router(projects_router)
app.include_router(brief_router)
app.include_router(research_router)
app.include_router(ideas_router)
app.include_router(export_router)
app.include_router(iteration_router)
app.include_router(analytics_router)

# Outreach routers
app.include_router(campaigns_router)
app.include_router(prospects_router)
app.include_router(messages_router)
app.include_router(outreach_router)

# Enhanced email system routers
app.include_router(webhooks_router)
app.include_router(sequences_router)
app.include_router(deliverability_router)
app.include_router(scraper_import_router)


# =============================================================================
# Exception Handlers
# =============================================================================

@app.exception_handler(CampaignGeneratorError)
async def campaign_error_handler(request: Request, exc: CampaignGeneratorError):
    """Handle custom application exceptions."""
    logger.error(f"{exc.error_code}: {exc.message}", extra=exc.details)
    return JSONResponse(
        status_code=400,
        content=exc.to_dict()
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.exception(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": {"type": type(exc).__name__} if settings.debug else {}
        }
    )


# =============================================================================
# Health & Info Endpoints
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "MAGA - Marketing AI Generation Assistant",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for container orchestration.
    
    Returns service health status and timestamp.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "maga-api"
    }


@app.get("/info")
async def system_info():
    """
    System information endpoint.

    Returns configuration and capability information.
    """
    config = get_project_config()

    return {
        "version": "1.0.0",
        "environment": settings.environment,
        "capabilities": {
            "ai_provider": config.ai_primary,
            "ai_model": config.ai_model,
            "export_formats": config.export_formats,
            "research_categories": len(config.research_categories),
            "scoring_criteria": len(config.scoring_criteria)
        },
        "defaults": {
            "country": config.default_country,
            "language": config.default_language,
            "num_ideas": config.num_ideas,
            "ideas_per_batch": config.ideas_per_batch
        }
    }


@app.get("/config/scoring")
async def get_scoring_config():
    """
    Get scoring configuration.

    Returns criteria, weights, and thresholds.
    """
    config = get_project_config()

    return {
        "criteria": [
            {
                "name": c.name,
                "weight": c.weight,
                "description": c.description
            }
            for c in config.scoring_criteria
        ],
        "thresholds": {
            "very_high": config.threshold_very_high,
            "high": config.threshold_high,
            "medium": config.threshold_medium,
            "low": config.threshold_low
        }
    }


@app.get("/cache/stats")
async def cache_stats():
    """
    Get cache statistics.

    Returns hit/miss rates and entry counts.
    """
    cache = get_ai_cache()
    return {
        "cache": cache.stats(),
        "settings": {
            "enabled": settings.cache_enabled,
            "ttl_memory": settings.cache_ttl_memory,
            "ttl_file": settings.cache_ttl_file
        }
    }


@app.post("/cache/clear")
async def clear_cache():
    """
    Clear all cached responses.

    Use with caution - this will increase API costs temporarily.
    """
    cache = get_ai_cache()
    memory_cleared = cache.memory_cache.clear()
    file_cleared = cache.file_cache.clear()

    logger.info(f"Cache cleared: {memory_cleared} memory, {file_cleared} file entries")

    return {
        "status": "cleared",
        "entries_removed": {
            "memory": memory_cleared,
            "file": file_cleared
        }
    }


@app.get("/config/categories")
async def get_research_categories():
    """
    Get research category configuration.

    Returns list of research categories with descriptions.
    """
    config = get_project_config()

    # Map categories to descriptions
    category_descriptions = {
        "01-mercado-general": "Análisis general del mercado",
        "02-competencia": "Análisis de competidores",
        "03-consumidor": "Insights del consumidor",
        "04-marca": "Análisis de la marca",
        "05-tendencias": "Tendencias del mercado",
        "06-medios": "Análisis de medios y canales",
        "07-cultural": "Contexto cultural",
        "08-digital": "Ecosistema digital",
        "09-referencias": "Referencias creativas",
        "10-investigacion-creativa": "Investigación creativa adicional"
    }

    return {
        "categories": [
            {
                "id": cat,
                "description": category_descriptions.get(cat, "")
            }
            for cat in config.research_categories
        ]
    }


# =============================================================================
# Run Application
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
