"""Typed failures crossing application subsystem boundaries."""


class ApplicationError(Exception):
    """Base class for failures suitable for presentation to the user."""


class RepositoryError(ApplicationError):
    """A game repository operation failed."""


class RevisionConflict(RepositoryError):
    """Stored data changed after the caller's snapshot was loaded."""


class InvalidStoredData(RepositoryError):
    """A persisted game document is malformed or inconsistent."""


class MapLibraryError(ApplicationError):
    """A configured map could not be loaded, validated, or stored."""


class RulesEngineError(ApplicationError):
    """The configured rules engine rejected an otherwise valid operation."""


class RenderingError(ApplicationError):
    """Map composition or image encoding failed."""
