"""Application coordinator and composition root."""

from diplomacy_app.application.composition import build_application
from diplomacy_app.application.service import ApplicationService

__all__ = ["ApplicationService", "build_application"]
