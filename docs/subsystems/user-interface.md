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
Image output sends only `ImageArtifact` values returned through the coordinator to the clipboard or a user-selected PNG file.
The shared map canvas removes native frames and overlays fixed-position compact zoom, Fog of War and hover-status controls without reserving layout space.
Map-facing layouts use narrow margins, spacing and splitter handles.
The canvas deliberately exposes one simple input model: a mouse wheel and compact buttons zoom, while dragging pans.

## Modules

- `application_window` creates the main window, binds global actions and swaps startup, game, new-game, map-manager and map-setup workspaces.
- `session_presenter` maps `SessionView` and typed failures onto widgets without adding domain decisions.
- `map_workspace` displays `MapScene`, fits a newly loaded game's map, preserves zoom and pan during later state refreshes, converts the visible viewport into `RenderRequest` values and transfers returned PNG artifacts through the clipboard or a native save-file chooser.
- `orders_workspace` owns compact non-stretching power cards with a shared-size rich canonical/editor surface, marks unparseable original lines in red, owns one inline text editor per configured power, warning expansion, final toggles, the unfinalised-power filter and collection of pending text before an order-overlay preview; card styling is scoped to the outer frame so nested text and stacked widgets retain stable geometry.
- `new_game_workspace` edits game metadata and game-specific starting state inside the main-window stack.
- `map_manager_workspace` selects reusable maps and starts existing-map or imported-SVG configuration.
- `map_wizard` coordinates the independently accessible Definition, Powers & start and Placement pages, keeps their immutable draft in sync, displays the effective adjacency graph beside the complete searchable YAML source, edits territory names, combines independently selectable placement layers using the fixed unit symbols, moves and rotates named-coast labels, drags every anchor and validates or saves from any tab; its current-game mode exposes only placement and saves only private presentation values.
- `map_setup_page` presents structured power, ownership, control, starting-unit and colour controls beside a preview composed by the gameplay renderer.
- `map_setup_model` converts the setup table's toolkit-independent row values into domain definitions and a validated starting state.
- `editor_widgets` contains the reusable YAML find bar and multiline display-name editor.
- `map_topology` builds the effective-adjacency SVG and immutable hover metadata without depending on or mutating Qt widgets.
- `background_tasks` executes blocking service calls and returns their completion to the GUI event thread.

## Dependencies

- Application Coordinator through `ApplicationService`.
- PySide6 Qt Widgets, Qt Core thread-pool facilities and Qt clipboard APIs.
