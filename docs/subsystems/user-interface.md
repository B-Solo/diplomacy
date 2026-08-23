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

`MapScene` is displayed as sanitised SVG with active content disabled.
The map workspace performs hover hit-testing only against the projected hotspots returned with that scene.
Clipboard integration accepts only `ImageArtifact` values returned through the coordinator.

## Modules

- `application_window` creates the main window, binds global actions and swaps startup, game and map-setup workspaces.
- `session_presenter` maps `SessionView` and typed failures onto widgets without adding domain decisions.
- `map_workspace` displays `MapScene`, owns zoom and pan state, and converts the visible viewport into `RenderRequest` values.
- `orders_workspace` owns one inline text editor per configured power, warning expansion, final toggles and the unfinalised-power filter.
- `map_setup_workspace` opens imported or existing reusable-map drafts, displays their sanitised SVG, previews armies or fleets at every applicable anchor, independently drags label, army, fleet and supply-centre anchors, and submits immutable draft snapshots for validation or saving.
- `background_tasks` executes blocking service calls and returns their completion to the GUI event thread.
- `clipboard` transfers returned PNG artifacts through the operating-system clipboard API.

## Dependencies

- Application Coordinator through `ApplicationService`.
- PySide6 Qt Widgets, Qt Core thread-pool facilities and Qt clipboard APIs.
