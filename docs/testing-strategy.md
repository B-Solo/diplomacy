# Testing Strategy

## Purpose

This document defines the verification approach used while implementing the subsystem designs.
Tests follow the application-owned contracts so third-party libraries and the desktop toolkit remain replaceable behind their adapters.

## Test Layers

### Contract and Domain Tests

Each subsystem has fast tests against its public protocol using immutable contract values and in-memory or temporary-directory collaborators.
These tests cover successful operations, structured user-input issues, typed operational failures and revision conflicts.
Order tests cover every phase, full names and abbreviations, canonicalisation, malformed lines, duplicate unit orders, omitted orders and engine validation attribution.
Visibility tests assert complete returned values rather than selected fields so restricted information cannot leak through newly added fields.

### Adapter Conformance Tests

The standard Rules Engine adapter is tested against small purpose-built maps and selected classic-map positions.
The suite covers ordinary and convoyed movement, support, bounces, cuts, dislodgement, retreats, split coasts, canals, builds, waives, disbands, invalid orders and every phase transition.
The Map Library tests safe SVG rejection, geometry suggestions, connection overrides, split coasts, compiled-map stability and authored-schema validation.
The storage codecs round-trip every schema value and reject unknown fields, unsupported versions and inconsistent identifiers.

### Repository Recovery Tests

Repository tests use real temporary filesystems.
Every phase-advancement installation step has an injected-failure case, followed by reopen and recovery, proving that the repository exposes either the old current phase or the fully committed next phase.
Single-file writes are tested for revision conflicts and preservation of the previous file when replacement fails.

### Rendering Tests

Renderer tests first inspect the composed SVG structure for deterministic layers, clipped bounds and absence of forbidden hidden-state data.
A small set of representative scenes is rasterised as golden PNGs for full-map, cropped, Fog of War, split-coast, convoy, invalid-order, retreat and adjustment cases.
Golden comparisons use a small pixel tolerance for platform rasterisation differences and always assert exact output dimensions and opaque bounds separately.

### User Interface Tests

Presenter and workspace tests run Qt in its offscreen mode and drive actions through the `ApplicationService` protocol.
They cover startup recovery, current-versus-historical editing, inline order editing, automatic clearing of `Final`, warning expansion, the unfinalised filter, adjudication confirmation, saved views and clipboard requests.
Map-setup tests verify maximised startup and standard close behaviour, reopen an existing reusable map in the main-window stack, access every configuration tab without sequencing, search both YAML editors through the platform-standard Find shortcut, merge focused power and starting-setup edits into the map YAML, save from an arbitrary tab, link classified rows and map highlights, verify the topology map is prioritised and its land and sea nodes use army and fleet anchors with readable labels and territory-YAML hover navigation, combine placement layers without artificial centre markers, exercise compact overlaid zoom controls and distinguish trackpad panning from mouse-wheel and pinch zooming, drag ordinary and split-coast anchors, constrain effective unit-asset previews and verify that an existing game's private map snapshot is unchanged.
A short manual smoke checklist covers native clipboard transfer, pointer-centred zooming, panning, high-DPI rendering and window behaviour on Windows and macOS.

## End-to-End Scenarios

The implementation is not considered complete until automated scenarios exercise these workflows through the coordinator and real repositories:

1. Import a structured SVG, correct generated map data, save the reusable map and create a game from it.
2. Enter, revise and finalise orders for several powers, resolve with and without the unfinalised warning, and reopen the advanced game.
3. Play through movement, retreat and adjustment phases, including phases with no required orders.
4. Navigate historical phases and verify that their submissions are readable but immutable.
5. Recall a saved crop in a later phase and export a pixel-identical frame containing only the selected map presentation.
6. Render every power perspective in a Fog of War game and verify that hidden state is absent from both the scene and copied image.
7. Reopen a self-contained game after application-level recent-game data has been removed.

## Fixtures and Determinism

Tests use a minimal synthetic map for focused rules and storage cases, the England map for irregular geometry and off-map links, and a classic-map fixture for standard-rule conformance.
Generated JSON and SVG use stable ordering so unexpected behavioural changes produce reviewable diffs.
Test fixtures contain no dependency-owned objects beyond the adapter tests.

## Continuous Verification

The default test command runs formatting, static typing, unit tests and non-GUI integration tests.
The portable unit and integration suite runs on Windows, macOS and Linux where continuous-integration capacity is available.
Headless Qt and raster golden tests run in the full verification command on Windows and macOS, with platform-specific golden baselines only where Qt rasterisation differs materially.
Dependency upgrades require the adapter conformance, recovery and golden suites before their pinned versions change.
