from __future__ import annotations

from pathlib import Path

import pytest

from diplomacy_app.map_library import FileMapLibrary


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def england(project_root):
    library = FileMapLibrary(
        user_maps_root=project_root / ".test-user-maps",
        bundled_maps_root=project_root / "maps",
    )
    return library.load(library.list()[0].map_id)
