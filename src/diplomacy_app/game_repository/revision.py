"""Content-derived repository revision tokens."""

from __future__ import annotations

import hashlib
from pathlib import Path

from diplomacy_app.domain.models import Revision


def revision_for_game(root: Path) -> Revision:
    digest = hashlib.sha256()
    authoritative = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and ".transactions" not in path.parts
        and not path.name.startswith(".")
        and path.suffix in {".yaml", ".json", ".svg", ".map"}
    ]
    for path in sorted(authoritative):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return Revision(digest.hexdigest())
