"""
Dependency Injection Container.

Centralizes service instantiation and dependency management.
"""

from dependency_injector import containers, providers

from .config import get_project_config, get_settings
from .database.engine import get_session
from .database.repositories import IdeaRepository, ProjectRepository, ResearchRepository
from .services.ai_client import AIClientManager, PromptLoader
from .services.analytics_service import AnalyticsService
from .services.brief_parser import BriefParserService
from .services.cache import AIResponseCache
from .services.export_service import ExportService
from .services.file_operations import FileOperationsService
from .services.ideas_service import IdeasService
from .services.iteration_service import IterationService
from .services.research_service import ResearchService
from .services.synthesis_service import SynthesisService
from .services.template_renderer import TemplateRenderer

# Outreach services
from .services.prospect_service import ProspectService
from .services.brand_brief_loader import BrandBriefLoader
from .services.message_validator import MessageValidator
from .services.email_service import EmailService
from .services.linkedin_service import LinkedInService
from .services.outreach_rate_limiter import OutreachRateLimiter


class Container(containers.DeclarativeContainer):
    """Application DI container."""

    # Configuration
    config = providers.Singleton(get_settings)
    project_config = providers.Singleton(get_project_config)

    # Database session (async context manager)
    db_session = providers.Resource(
        get_session
    )

    # Repositories
    project_repository = providers.Factory(
        ProjectRepository,
        session=db_session
    )

    idea_repository = providers.Factory(
        IdeaRepository,
        session=db_session
    )

    research_repository = providers.Factory(
        ResearchRepository,
        session=db_session
    )

    # Core Services
    ai_cache = providers.Singleton(AIResponseCache)

    prompt_loader = providers.Singleton(PromptLoader)

    ai_manager = providers.Singleton(AIClientManager)

    file_service = providers.Singleton(
        FileOperationsService,
        project_repository=project_repository
    )

    template_renderer = providers.Singleton(TemplateRenderer)

    # Business Services
    brief_parser = providers.Factory(
        BriefParserService
    )

    research_service = providers.Factory(
        ResearchService,
        research_repository=research_repository
    )

    synthesis_service = providers.Factory(
        SynthesisService
    )

    ideas_service = providers.Factory(
        IdeasService,
        idea_repository=idea_repository
    )

    export_service = providers.Factory(
        ExportService
    )

    iteration_service = providers.Factory(
        IterationService
    )

    analytics_service = providers.Factory(
        AnalyticsService,
        ai_manager=ai_manager,
        file_service=file_service
    )

    # Outreach Services
    prospect_service = providers.Singleton(ProspectService)

    brand_brief_loader = providers.Singleton(BrandBriefLoader)

    message_validator = providers.Singleton(MessageValidator)

    email_service = providers.Factory(EmailService)

    linkedin_service = providers.Factory(LinkedInService)

    outreach_rate_limiter = providers.Singleton(OutreachRateLimiter)


# Global container instance
container = Container()


# Backward compatibility functions
def get_container() -> Container:
    """Get the DI container."""
    return container
