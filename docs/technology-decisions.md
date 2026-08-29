# Technology Decisions

## Purpose

This document records the concrete implementation dependencies selected for the application and the evidence supporting the Rules Engine adapter.
The subsystem boundaries in [Functional Structure](functional-structure.md) remain authoritative when a dependency is replaced.

## Rules Engine Confirmation

The standard Rules Engine uses `diplomacy` 1.1.2, pinned to upstream commit `df1d0892ce27501386d8dbf2e9948055ea960445` and vendored with its licence and provenance.
Vendoring gives the application a reproducible version of an inactive upstream project and permits local compatibility maintenance.

The package was exercised under Python 3.13 with the following results:

- A custom map loaded successfully from an arbitrary filesystem path.
- The standard map validated with split coasts, canal-like fleet movement through Kiel and Constantinople, and the impassable Switzerland province.
- Map adjacency is data-driven, so an off-map connection is represented identically to a visually adjacent connection.
- Strict order submission rejected illegal moves, fleet movement onto land and unreachable support with distinct human-readable errors.
- Processing exposed stable result markers including `VOID`, `NO_CONVOY`, `BOUNCE`, `CUT`, `DISLODGED`, `DISRUPTED` and `DISBAND`.
- `NO_CHECK` retained recognised invalid movement orders for adjudication, applied an effective hold and produced `VOID`.
- Phase advancement retains Spring, Summer, Fall, Winter and Year End even when no decisions are required.
- The focused upstream engine and map tests passed under Python 3.13.

The adapter validates recognised candidates in source order on an isolated strict game instance and attributes only the errors added by each submission attempt.
Adjudication uses a separately reconstructed game with `NO_CHECK` enabled and explicit five-phase progression; movement results are carried into the following retreat phase as pending resolution state.
Order Processing prevents unrecognised text from reaching the package because the package assumes recognisable order structure.

The Map Library compiles each validated application map into the package's text map format.
The compiled `_engine.map` file is derived from `_compiled-map.json` after successful map validation.

## Desktop Toolkit

The application uses PySide6 with Qt Widgets.
Qt Widgets suits the form-heavy gamemaster workflow, while `QGraphicsView` supplies mature zooming, panning and coordinate transforms for maps of different sizes.
`QThreadPool` runs blocking coordinator calls outside the event thread, while `QClipboard` and the native file chooser provide image output integration.

The same Qt SVG implementation displays and exports composed scenes.
`QSvgRenderer` renders a `MapScene` into a `QGraphicsView` for interaction and into a bounded `QImage` through `QPainter` for PNG export.
Using one renderer avoids display-versus-clipboard differences caused by separate SVG engines.

## Platform Support

Windows is the primary runtime platform for the finished application.
The application also supports testing and use on macOS, while the toolkit-independent test suite remains runnable in Linux development environments.
Filesystem paths, application-data locations, clipboard access and high-DPI behaviour use Qt, `pathlib` and `platformdirs` abstractions instead of platform-specific assumptions.
Manual desktop acceptance is performed on Windows and macOS.

## SVG and Geometry

`defusedxml.ElementTree` parses imported SVG with DTDs, entities and external references forbidden.
The importer then applies an explicit element and attribute allowlist and rejects external URLs, scripts, event attributes, animation and processing instructions before any Qt component sees the content.

`svgelements` converts SVG paths and basic shapes into transformed geometric paths.
Shapely converts their flattened boundaries into polygons, detects likely shared borders, builds spatial indexes and calculates candidate interior anchors.
Geometry output remains a suggestion until the reviewed defaults and explicit exceptions are materialised as effective topology.

## Structured Data

JSON stores machine-managed application state, compiled maps, saved views, phase state and order records using the standard-library encoder with deterministic key ordering and indentation.
YAML stores each authored configured map and static game configuration that a gamemaster may inspect or edit.
PyYAML parses YAML through `safe_load`; the application preserves authored map text verbatim and uses `safe_dump` only for newly generated content.

Pydantic 2 storage models validate and version data at repository boundaries before conversion to immutable application dataclasses.
Unknown fields are rejected within the current schema version so spelling errors cannot silently change game behavior.
`platformdirs` locates application configuration and the reusable map library on each desktop operating system.

## Filesystem Consistency

Ordinary single-file changes use a temporary sibling file, flush file data, replace the destination atomically and flush the containing directory where supported.
Phase advancement changes several files and therefore uses the recoverable transaction described in [Storage Schema](storage-schema.md#recoverable-phase-advancement).

## Dependency Boundary

Only the User Interface imports PySide6 widget types.
Only Map Rendering imports Qt SVG and painting types.
Only Map Library imports XML and geometry libraries.
Only storage codecs import Pydantic and PyYAML.
Only the standard Rules Engine adapter imports the vendored `diplomacy` package.

## References

- [`diplomacy` source](https://github.com/diplomacy/diplomacy)
- [`diplomacy` game API](https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.game.html)
- [`diplomacy` map API](https://diplomacy.readthedocs.io/en/stable/api/diplomacy.engine.map.html)
- [`diplomacy` result codes](https://diplomacy.readthedocs.io/en/stable/api/diplomacy.utils.order_results.html)
- [Qt for Python](https://www.qt.io/development/qt-framework/python-bindings)
- [`QSvgRenderer`](https://doc.qt.io/qtforpython-6/PySide6/QtSvg/QSvgRenderer.html)
- [`defusedxml`](https://github.com/tiran/defusedxml)
- [`svgelements`](https://github.com/meerk40t/svgelements)
- [Shapely](https://shapely.readthedocs.io/en/stable/manual.html)
- [Pydantic](https://pydantic.dev/docs/validation/latest/get-started/)
- [`platformdirs`](https://platformdirs.readthedocs.io/en/stable/tutorial.html)
