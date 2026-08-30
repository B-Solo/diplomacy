from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from diplomacy_app.map_library import FileMapLibrary


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def england(project_root):
    library = FileMapLibrary(project_root / "maps")
    return library.load(library.list()[0].map_id)


@pytest.fixture(scope="session")
def england_draft(project_root):
    library = FileMapLibrary(project_root / "maps")
    return library.load_draft(library.list()[0].map_id)


@pytest.fixture
def configured_maps(tmp_path, project_root):
    maps_root = tmp_path / "maps"
    shutil.copytree(project_root / "maps", maps_root)
    return FileMapLibrary(maps_root)
