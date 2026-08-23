# Diplomacy Gamemaster

Diplomacy Gamemaster is a local desktop application for running custom-map Diplomacy games.
It records player orders, resolves phases simultaneously, preserves complete game history, produces map images, and supports optional per-power Fog of War views.

The application includes the configured six-player England map and a map wizard for importing or correcting structured SVG maps.
Player communication and player-facing accounts remain outside the application.

## Windows setup

Install 64-bit Python 3.13 from [python.org](https://www.python.org/downloads/windows/) and enable the Python launcher during installation.

After cloning the repository, open Command Prompt in the repository folder and run:

```bat
setup-windows.bat
```

The script creates `.venv`, installs the pinned vendored adjudicator and application dependencies, and installs development verification tools.
It does not modify the system Python installation.

Start the application with:

```bat
run-windows.bat
```

Run `setup-windows.bat` again after pulling changes to `pyproject.toml`, `constraints.txt`, or the vendored adjudicator.

## Everyday workflow

1. Start the application and open a recent game, select an existing self-contained game folder, or create a game.
2. Use the Map workspace to choose position or order display, labels, a saved crop, and an optional Fog of War perspective.
3. Select **Copy map** to put exactly the displayed map region on the clipboard without application controls.
4. Use the Orders workspace to enter one player submission per power, review canonical interpretations and warnings, and mark submissions final.
5. Select **Resolve and advance** when the phase is ready.

Historical phases remain selectable and read-only.
Spring, Summer, Fall, Winter, and Year End are retained even when a retreat or adjustment phase has no decisions.

## Order notation

The editor accepts full territory names or configured three-letter abbreviations without case sensitivity.
Examples include:

```text
A London H
F NTH - Yorkshire
A Wales S F London
F North Sea C A London - Belgium
A Yorkshire R Lancashire
A London B
F NTH D
Waive
```

The application preserves the original submission separately from its canonical interpretation.
Illegal and unrecognised lines remain recorded with their issues, and missing or invalid orders receive the standard phase-specific behavior.

## Creating and correcting maps

Select **New game**, then either edit a configured map or import a structured SVG.
Every relevant SVG shape or group must have a unique identifier.

The map wizard provides four stages:

- Classify identified SVG regions as playable territory, impassable region, or decoration.
- Edit and validate the durable `map.yaml` source while inspecting the complete compiled topology.
- Drag label, army, fleet, split-coast, and supply-centre anchors on the map.
- Supply optional custom army and fleet SVG symbols.

Geometry supplies ordinary adjacency suggestions.
The authored YAML records additions, removals, split coasts, canals, and off-map links.
Saving a correction creates a user-owned configured-map copy and does not silently alter an existing game's private map snapshot.

The supplied England map is reconstructed from the Anarchy in the UK variant.
Its source and licence information are recorded in [maps/england/SOURCE.md](maps/england/SOURCE.md).

## Game folders

Each game folder is portable and self-contained.
It includes static game settings, saved map views, an immutable private map snapshot, every reached phase state, original order text, canonical orders, validation, and adjudication results.

Phase advancement uses recoverable redo transactions.
Opening a game automatically completes an interrupted prepared transaction before exposing any phase snapshot.
Content-derived revision tokens prevent stale editor or external filesystem changes from being overwritten.

Application-level recent-game information is stored in the operating system's normal per-user application configuration directory.
Deleting that record does not affect or prevent reopening a game folder.

## Development on macOS or Linux

Create the environment with Python 3.13:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -c constraints.txt -e vendor/diplomacy
.venv/bin/python -m pip install -c constraints.txt -e '.[dev]'
```

Start the application with:

```bash
.venv/bin/python -m diplomacy_app
```

On a headless Linux machine, set `QT_QPA_PLATFORM=offscreen` only for automated UI tests.

## Verification

Run the complete local verification gate with:

```bash
scripts/verify.sh
```

That command runs Ruff formatting checks, application-wide type checking, and the automated unit, integration, rendering, repository, coordinator, and headless Qt suites.

## Adjudicator provenance

The standard rules adapter vendors `diplomacy` 1.1.2 from upstream commit `df1d0892ce27501386d8dbf2e9948055ea960445`.
The upstream licence and notices are retained under `vendor/diplomacy/`.
The application generates a deterministic engine map for each validated custom map and keeps dependency-owned types behind the rules-engine adapter.
