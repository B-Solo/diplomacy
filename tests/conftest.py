from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from diplomacy_app.domain.models import MapId
from diplomacy_app.map_library import FileMapLibrary


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def england(project_root):
    library = FileMapLibrary(project_root / "maps")
    return library.load(MapId("england"))


@pytest.fixture(scope="session")
def england_draft(project_root):
    library = FileMapLibrary(project_root / "maps")
    return library.load_draft(MapId("england"))


@pytest.fixture
def configured_maps(tmp_path, project_root):
    maps_root = tmp_path / "maps"
    # Keep this historical fixture focused on the England map. Other
    # configured maps are tested explicitly and should not change which map
    # the existing application tests select by default.
    shutil.copytree(project_root / "maps/england", maps_root / "england")
    return FileMapLibrary(maps_root)
