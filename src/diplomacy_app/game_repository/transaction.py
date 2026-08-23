"""Recoverable redo transactions for multi-file phase advancement."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from diplomacy_app.domain.errors import RepositoryError


def _flush_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _flush_directory(path.parent)


def atomic_json(path: Path, value: object) -> None:
    _atomic_bytes(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def recover(root: Path) -> None:
    marker = root / ".transaction.json"
    if not marker.exists():
        return
    try:
        intent = json.loads(marker.read_text(encoding="utf-8"))
        stage = root / ".transactions" / str(intent["id"])
        manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        for item in manifest["files"]:
            target = root / item["target"]
            staged = stage / item["staged"]
            if (
                target.exists()
                and hashlib.sha256(target.read_bytes()).hexdigest() == item["sha256"]
            ):
                continue
            if not staged.exists():
                raise RepositoryError(f"Transaction staging file is missing: {staged}")
            if hashlib.sha256(staged.read_bytes()).hexdigest() != item["sha256"]:
                raise RepositoryError(f"Transaction staging digest is invalid: {staged}")
            _atomic_bytes(target, staged.read_bytes())
        marker.unlink()
        shutil.rmtree(stage)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise RepositoryError(f"Could not recover interrupted game transaction: {exc}") from exc


def commit_files(root: Path, files: list[tuple[str, bytes]], final_target: str) -> None:
    """Install files as a recoverable transaction, installing state last."""
    transaction_id = uuid.uuid4().hex
    stage = root / ".transactions" / transaction_id
    stage.mkdir(parents=True)
    ordered = [item for item in files if item[0] != final_target]
    ordered.extend(item for item in files if item[0] == final_target)
    entries: list[dict[str, str]] = []
    for index, (target, data) in enumerate(ordered):
        staged_name = f"file-{index}"
        staged = stage / staged_name
        with staged.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        entries.append(
            {"target": target, "staged": staged_name, "sha256": hashlib.sha256(data).hexdigest()}
        )
    atomic_json(stage / "manifest.json", {"schema_version": 1, "files": entries})
    _flush_directory(stage)
    atomic_json(root / ".transaction.json", {"schema_version": 1, "id": transaction_id})
    recover(root)
