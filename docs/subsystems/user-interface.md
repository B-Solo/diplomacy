# User Interface

## Responsibility

The User Interface adapts desktop events and widgets to the `ApplicationService` contract defined in [Subsystem API Contracts](../api-contracts.md).
It owns transient presentation state and delegates every persisted or domain operation to the Application Coordinator.

## External API

The subsystem provides the executable application's desktop entry point.
It consumes `ApplicationService` for startup, game and phase selection, order editing, map composition, image export and map setup.

## Implementation Notes

The UI renders returned snapshots rather than maintaining a second editable domain model.
Blocking import, adjudication and rasterisation calls run outside the GUI event thread, with completion marshalled back to that thread.
The UI disables duplicate mutation actions while a call is active and presents typed application failures without interpreting dependency exceptions.
Application workflows are pages in the main-window stack, with inline status and confirmation regions; only native filesystem selection leaves the window.
The entry point opens the main window maximised, converts terminal interrupts into normal Qt shutdown requests and restores the process signal handler after the event loop exits.
The main window binds Qt's platform-standard Close shortcut so macOS supplies `Cmd+W` and other platforms use their native equivalent.

`MapScene` is displayed as sanitised SVG with active content disabled.
The map workspace performs hover hit-testing only against the projected hotspots returned with that scene.
Clipboard integration accepts only `ImageArtifact` values returned through the coordinator.
The shared map canvas removes native frames and overlays fixed-position compact zoom, Fog of War and hover-status controls without reserving layout space.
Map-facing layouts use narrow margins, spacing and splitter handles, while the canvas distinguishes pixel-based or touchpad wheel events from mouse-wheel angle events so two-finger scrolling pans, a mouse wheel zooms and native trackpad magnification gestures provide smooth pointer-centred zooming.

## Modules

- `application_window` creates the main window, binds global actions and swaps startup, game, new-game, map-manager and map-setup workspaces.
- `session_presenter` maps `SessionView` and typed failures onto widgets without adding domain decisions.
- `map_workspace` displays `MapScene`, fits a newly loaded game's map, preserves zoom and pan during later state refreshes, and converts the visible viewport into `RenderRequest` values.
- `orders_workspace` owns one inline text editor per configured power, warning expansion, final toggles and the unfinalised-power filter.
- `new_game_workspace` edits game metadata and game-specific starting state inside the main-window stack.
- `map_manager_workspace` selects reusable maps and starts existing-map or imported-SVG configuration.
- `map_wizard` presents independently accessible configuration tabs, provides inline wrapping search for both YAML editors, links classified rows with SVG hover highlights, displays a large readable army/fleet-anchor adjacency graph over a faded map, links topology nodes to highlighted territory YAML blocks, merges focused power and starting-setup YAML into the complete document, combines independently selectable placement layers, moves and rotates named-coast labels, previews effective unit assets at constrained scale, drags every anchor and validates or saves their shared immutable draft from any tab.
- `background_tasks` executes blocking service calls and returns their completion to the GUI event thread.
- `clipboard` transfers returned PNG artifacts through the operating-system clipboard API.

## Dependencies

- Application Coordinator through `ApplicationService`.
- PySide6 Qt Widgets, Qt Core thread-pool facilities and Qt clipboard APIs.
