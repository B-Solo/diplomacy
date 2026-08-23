"""Construct production subsystem implementations."""

from diplomacy_app.application.service import ApplicationService
from diplomacy_app.game_repository import FileGameRepository
from diplomacy_app.map_library import FileMapLibrary
from diplomacy_app.rendering import MapRenderer
from diplomacy_app.rules_engine import StandardRulesEngine
from diplomacy_app.visibility import VisibilityProjector


def build_application() -> ApplicationService:
    return ApplicationService(
        FileGameRepository(),
        FileMapLibrary(),
        StandardRulesEngine(),
        VisibilityProjector(),
        MapRenderer(),
    )
