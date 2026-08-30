# User Interface Contract

## Summary

This document defines the gamemaster-facing interface for the Diplomacy application.
It is a repository-tracked living specification and describes agreed behaviour in present tense.

The interface prioritises the two activities performed throughout a game: preparing player-facing map images and recording orders before adjudication.
Map creation and game creation are separate, infrequent workflows that remain available without adding clutter to ordinary play.

## Problem Definition

The gamemaster receives player orders outside the application, records them, adjudicates each season and distributes map images.
The interface must make those tasks quick while preventing a restricted Fog of War view, an unfinished submission or application chrome from accidentally appearing in a player-facing image.

Player communication occurs outside the application using map images copied by the gamemaster.

## Scope, Goals, and Non-Goals

### Goals

- Keep the everyday interface centred on the map and submitted orders.
- Maximise usable map area by keeping supporting copy brief and placing compact map controls over the canvas.
- Preserve the player's original order text while presenting a consistent canonical interpretation.
- Make the selected season, display mode and Fog of War perspective unambiguous.
- Produce repeatable, tightly bounded map images for use across multiple seasons.
- Support reusable custom maps without requiring their configuration files to be written entirely by hand.
- Keep historical seasons readily inspectable and read-only.

### Non-Goals

- Player accounts, player order submission and player communication.
- A vector drawing application for creating territory shapes.

## Background and References

- [Functional specification](functional-specification.md)
- [Classic map reference](../references/classic-map.jpg)
- [England map reference](../references/england-map.png)
- [Official Diplomacy rules](https://www.hasbro.com/common/instruct/diplomacy.pdf)

## Functional Requirements

### Application and Game Navigation (AN)

- **AN.1:** On launch, the application opens the last-used game and selects its latest season.
- **AN.2:** If the last-used game is unavailable, or no game has been opened before, the application shows recent games together with `Open game folder` and `New game` actions.
- **AN.3:** The in-game header identifies the open game and provides a compact way to open, create or switch games.
- **AN.4:** The header always shows both `Map` and `Orders` workspace choices in a prominent high-contrast switch whose active workspace is unmistakable.
- **AN.5:** The application opens maximised to the usable desktop area rather than in borderless full-screen mode.
- **AN.6:** The platform-standard close-window shortcut closes the application, including `Cmd+W` on macOS.
- **AN.7:** When launched from a terminal, `Ctrl+C` requests a normal application shutdown without a traceback.
- **AN.8:** Game, season and perspective context persists when switching between the primary workspaces.
- **AN.9:** Game creation and reusable-map management replace the main workspace temporarily and return to the preceding application context when completed or cancelled.
- **AN.10:** Application workflows, validation messages and confirmations remain inside the main window; operating-system file and folder choosers may use native windows.
- **AN.11:** The current game's choices open the complete map editor for its private map snapshot.
- **AN.12:** All workspaces use an application-owned light palette and platform-available fonts; interactive controls and their normal, selected, hovered and disabled states maintain explicit foreground/background contrast rather than relying on the desktop theme.
- **AN.13:** Recent games can be permanently deleted from the game choices after an in-window confirmation identifies the game folder and warns that deletion cannot be undone; deleting the current game returns to the no-game state.
- **AN.14:** Game creation asks for a parent location, previews the destination and creates a safe top-level folder derived from the game name beneath that location.

### Season Navigation (SN)

- **SN.1:** The application opens at the newest season for which a state exists.
- **SN.2:** A compact previous button, full-label-width season selector and next button navigate history without truncating season names.
- **SN.3:** Season labels contain only the season and year, for example `Spring 1901` or `Year End 1901`.
- **SN.4:** The history includes Spring, Summer, Fall, Winter and Year End for every year, including retreat or build seasons in which no orders are required.
- **SN.5:** The selected season is identified by the season selector alone; the latest season has no redundant `Current` annotation.
- **SN.6:** Historical orders are visible but read-only.
- **SN.7:** Previous and next buttons are disabled and visibly subdued when no earlier or later recorded season exists.

### Map Workspace (MW)

- **MW.1:** The map occupies the available workspace while preserving the SVG view box and aspect ratio; surrounding chrome uses compact controls, minimal margins and overlays instead of persistent map-reducing status rows.
- **MW.2:** Loading a map fits the entire map into the workspace without stretching it; later state refreshes preserve the user's viewport.
- **MW.3:** The gamemaster zooms with a mouse wheel or visible controls and pans by dragging.
- **MW.4:** Mouse-wheel zoom is centred on the pointer.
- **MW.5:** Compact `−`, read-only current-percentage, `+` and `Fit` controls overlay the map; wheel and button zoom use the same discrete levels.
- **MW.6:** `Fit` returns to the full-map view without changing the map state.
- **MW.7:** Pan is clamped to the map bounds.
- **MW.8:** The map display switches between `Position` and `Orders`, and an explicit `Preview orders on map` action follows the contiguous perspective, display-mode and label controls in the Map toolbar without separating them; the same action is available from the Orders workspace.
- **MW.8a:** During Summer and Winter, the map always overlays the immediately preceding movement phase's recorded orders over the unmoved position; a `Successful movements only` toggle hides movement-related orders whose adjudication outcome was unsuccessful.
- **MW.9:** Territory labels switch between display names and three-letter codes, never displaying both modes together; display names support centred explicit line breaks and otherwise wrap long text at spaces or ampersands.
- **MW.10:** Land abbreviations have only their initial letter capitalised, while sea abbreviations are uppercase.
- **MW.11:** The Map toolbar contains a readable named-view selector with a visible dropdown indicator and full-name tooltips, plus `Save current`, `Copy map` and `Save image` actions.
- **MW.12:** Saving a current-game map warns that every phase is affected, keeps the private map ID immutable, and reparses saved order submissions without re-adjudicating completed phases.

### Saved Views and Image Copying (IC)

- **IC.1:** A saved view records geographic bounds, aspect ratio and output pixel dimensions.
- **IC.2:** A saved view does not record season, Fog of War perspective, label mode or order-overlay state.
- **IC.3:** Recalling a saved view does not resize the application window.
- **IC.4:** `Full map` is a built-in saved view.
- **IC.5:** Saved views persist with the game so the same framing can be reused in later seasons.
- **IC.6:** `Copy map` copies the map exactly as currently presented, including its position or order display, territory-label mode, units and permitted Fog of War content.
- **IC.7:** The copied image excludes application controls, badges, outlines and any workspace beyond the SVG map bounds.
- **IC.8:** When a saved or current view reaches a map edge, the copied image aligns exactly with that edge rather than including padding outside it.
- **IC.9:** After recalling `Full map` or a named saved view, any subsequent pan or zoom changes the view selector to `Custom view`; programmatic rendering and window resizing do not clear the selection.
- **IC.10:** `Save image` writes the same bounded PNG that `Copy map` places on the clipboard, using a native file chooser.
- **IC.11:** Copied and saved images preserve the selected geographic bounds' aspect ratio without stretching; saved views retain fitted pixel dimensions so repeated output has the same size.

### Fog of War (FW)

- **FW.1:** Full-visibility games do not show perspective controls.
- **FW.2:** Fog of War games provide a `Viewing as` selector containing the gamemaster and each power.
- **FW.3:** Selecting a power adds a prominent persistent Fog of War badge and a coloured outline outside the copyable map region.
- **FW.4:** While a power is selected, the copy action names that power, for example `Copy Red view`.
- **FW.5:** A territory outside the selected power's visibility is grey and retains only its selected territory label.
- **FW.6:** A hidden territory reveals no controller colour, unit, supply-centre marker, ownership, order graphic or other state-dependent content.
- **FW.7:** Visibility adjacency is the union of army and fleet connections between territories, including exceptional and off-map connections, regardless of the observing unit's type.
- **FW.8:** A dislodged unit continues to provide visibility from its current territory during a retreat phase.

### Territory, Unit and Supply-Centre Rendering (TR)

- **TR.1:** The current controller determines a playable land territory's colour; each map configures its sea, unclaimed-land and inaccessible-region colours.
- **TR.2:** Successful occupation changes territorial control, while an empty territory retains its controller.
- **TR.3:** Supply-centre ownership is independent of current occupation and is represented by a sharp star filled with a slightly darker version of its owner's colour.
- **TR.4:** Neutral supply centres use a neutral star.
- **TR.5:** Each map provides one reusable army symbol and one reusable fleet symbol.
- **TR.6:** All units of a type share the corresponding map symbol.
- **TR.7:** A unit symbol is filled with a slightly darker version of its power colour and has a still-darker outline.
- **TR.8:** Unit and supply-centre symbols are positioned using map-defined anchors and are included in copied images.
- **TR.9:** During a retreat phase, a dislodged unit remains visible at its original territory with a small `R` marker.
- **TR.10:** When another unit occupies that territory, the dislodged unit is offset so both units remain legible.

### Order Graphics (OG)

- **OG.1:** A move is a solid arrow from its unit to its destination whose shaft ends beneath the triangular head without a protruding rounded target dot.
- **OG.2:** Support for a move is a dotted cubic curve with the same stroke weight as a move; its join adapts to the supporter's position, remains clear of the move arrowhead and turns gradually through a long final tangent so the paths visibly merge without substantially overlapping.
- **OG.3:** Support for a hold is a dotted line ending at the supported unit.
- **OG.4:** A convoy order is a pronounced wavy line from the convoying fleet to the convoyed move arrow, normally joining the portion of the route within that fleet's territory.
- **OG.5:** A convoyed move uses a smoothed piecewise arrow through the relevant convoy chain when a straight arrow would misleadingly cross land.
- **OG.6:** A hold is a short, heavy solid black underline at the map-configured offset for that unit type.
- **OG.7:** An invalid movement order is displayed as a dashed underline because holding is its effective behaviour.
- **OG.8:** A build or disband displays the affected unit with a `+` or `−` over it.
- **OG.9:** Order graphics remain visually subordinate to the map and units.
- **OG.10:** A waived build appears in the canonical order list without a map graphic.

### Orders Workspace (OW)

- **OW.1:** The current season displays one power panel for every configured power.
- **OW.2:** Power panels use a two-column layout on wide windows and a single column on narrow windows; each non-stretching card has a compact power header and an edge-to-edge order surface that occupies most of its height.
- **OW.3:** A power panel shows the power and its orders in canonical compact notation using configured territory abbreviations; games with order finalisation enabled also show its final state.
- **OW.4:** Selecting the canonical order text reveals a same-height plain-text editor containing the player's exact original submission, including its names, abbreviations, whitespace, punctuation and line breaks, without resizing its power panel or grid row.
- **OW.5:** The editor accepts one order per line using territory names or abbreviations, including `A|F <unit territory> - <destination>` for moves and `A|F <supporting territory> S A|F <supported territory> - <destination>` for support moves, with multi-word locations and `->` accepted in place of `-`; Enter inserts a line break, and parsing tolerates reasonable differences in case, whitespace and punctuation.
- **OW.6:** Leaving an editor, including by selecting another power's order editor, reparses the complete original submission and returns the previous panel to canonical presentation; the newly selected editor remains open and focused, and selecting any canonical presentation restores its exact original text rather than the canonical text.
- **OW.7:** Changes are saved and validated as they are entered without replacing or closing the active editor.
- **OW.8:** When order finalisation is enabled, editing any text clears that power's `Final` state.
- **OW.9:** When order finalisation is enabled, each editable power panel provides an explicit `Orders final` action.
- **OW.10:** When order finalisation is enabled, the workspace provides an `Unfinalised only` filter and final count; neither is present otherwise.
- **OW.11:** During reached retreat and build seasons, powers with no legal decisions have inert `No orders required` panels and count as final when finalisation is enabled.
- **OW.12:** An order issue is represented only by a warning flag until selected.
- **OW.13:** Selecting a warning flag expands the affected panel and reveals the warning.
- **OW.14:** `Preview orders on map` saves any text awaiting validation, opens the map in Orders mode and draws the effective order arrows and markers over the current position without adjudicating or moving units.
- **OW.15:** A compact syntax guide remains visible above the order cards with concrete hold, move, support, retreat, build, disband and waive examples, explicitly identifying its location names as replaceable examples.

### Order Interpretation (OI)

- **OI.1:** Canonical order display uses conventional compact Diplomacy notation.
- **OI.2:** Recognised valid orders display their canonical interpretation.
- **OI.3:** A recognised invalid order is retained with its validation reason and receives the standard phase-specific default effect.
- **OI.4:** An unrecognisable line is retained even when it cannot be associated with a unit and appears in the canonical summary as its original text in red followed by `(??)`.
- **OI.5:** A missing order has no fabricated submitted text or source line and receives the standard phase-specific default effect.
- **OI.6:** The default order display omits engine outcome categories such as bounce, no convoy, cut and dislodged.
- **OI.7:** Submission validation and the adjudicator's later `VOID` result remain distinct.
- **OI.8:** The `ui.explain_adjudication_outcomes` game-YAML setting controls optional adjudication explanations and defaults to `false`.
- **OI.9:** When optional explanations are enabled, hovering an order graphic may display its engine outcome category.
- **OI.10:** In a movement phase, an invalid order or an omitted unit order becomes a hold.
- **OI.11:** In a retreat phase, an invalid or omitted retreat becomes a disband.
- **OI.12:** In a build phase, an invalid or omitted build becomes a waived build, and the editor accepts an explicit `Waive` order.
- **OI.13:** In a disband phase, the Rules Engine selects any disbands still required after valid submitted disbands have been applied.
- **OI.14:** Multiple submitted orders for the same unit are invalid as a group and receive the applicable phase-specific default.
- **OI.15:** Original submitted text and parsed canonical orders remain separate values; validation, order previews and adjudication consume the parsed orders without overwriting the original text.
- **OI.16:** Movement, retreat, disband, build and waive order kinds are accepted only in their applicable phases; an invalid phase order receives the existing phase-specific default effect.

### Adjudication and Advancement (AA)

- **AA.1:** The Orders workspace provides one `Resolve and advance` action.
- **AA.2:** With order finalisation disabled, the action adjudicates immediately; with it enabled, adjudication is immediate when all relevant powers are final.
- **AA.3:** Only when order finalisation is enabled and relevant powers are not final, the action warns the gamemaster and names those powers before allowing adjudication to continue.
- **AA.4:** Successful adjudication records the submitted orders and results, retains the next retreat or adjustment season even when it has no legal decisions, creates its displayed state, selects it and opens the Map workspace.
- **AA.4a:** Resolving Spring or Fall records the movement result without moving the displayed units into the next retreat season; resolving Summer or Winter applies the pending movement and every retreat before creating the next movement or Year End state.
- **AA.5:** An adjudication or file-write failure leaves the current season unchanged and displays the error.

### Game and Map Creation (GC)

- **GC.1:** `New game` first offers existing configured maps and an `Import SVG and create map` path.
- **GC.2:** Completing map import saves a reusable configured map and returns to game creation.
- **GC.3:** Creating another game from that map reuses its configured powers, colours, home supply centres, initial ownership, initial control and starting units.
- **GC.4:** A game's starting year, season, units, phase-required retreat state, supply-centre ownership and territory control may be adjusted without modifying the reusable map defaults.
- **GC.5:** Game-specific starting adjustments retain the configured map's powers, colours and home supply centres.
- **GC.6:** Map import accepts a prepared structured SVG in which every relevant territory shape or group has a unique identifier.
- **GC.7:** Map import associates existing SVG shapes and groups with map elements.
- **GC.8:** Imported shapes are classified as playable land, playable sea, impassable region or decorative/background content.
- **GC.9:** Only playable regions require a canonical territory name, optional multiline display name, abbreviation, topology and placement anchors.
- **GC.10:** The importer calculates initial label, army, fleet and supply-centre anchors and provides a visual Placement tab in which each anchor can be dragged independently.
- **GC.11:** Split coasts have separate fleet anchors and visible named-coast labels with independently configurable anchors and rotations.
- **GC.12:** The importer generates likely adjacency from SVG geometry and assumes that every coastal province has one continuous coast.
- **GC.13:** The generated ordinary topology is combined with explicit additions and removals, then materialised as the complete topology used for play.
- **GC.14:** Definition gives its graphical adjacency preview approximately three quarters of the initial split, includes readable territory and split-coast nodes, exposes local connection overrides alongside the complete effective topology and provides inline, wrapping text search through the platform-standard Find shortcut.
- **GC.15:** The map-configuration editor supports split-coast connections, canals, off-map links, missed links and removal of incorrectly generated links through text.
- **GC.16:** The saved `map.yaml` remains directly editable outside the application.
- **GC.17:** A focused Powers & start tab uses structured fields to edit the starting phase, powers, power and map colours, home and starting supply-centre ownership, initial territory control and starting units, then writes those sections to the shared `map.yaml` and regenerates an exact gameplay-renderer preview.
- **GC.18:** Every map uses the fixed army and fleet symbols shown in Placement; map-specific unit artwork is not configurable.
- **GC.19:** An existing reusable map can be reopened in the map-configuration editor without re-importing its SVG.
- **GC.20:** Reopening a map provides the same visual Placement tab as initial import, including independent territory-label, named-coast-label, army, fleet, split-coast fleet and supply-centre anchors.
- **GC.21:** Saving an edited reusable map changes the defaults used for games created afterwards and does not modify the private map snapshots of existing games.
- **GC.22:** The visual Placement tab provides independent `Armies`, `Fleets`, `Supply centres`, territory-label and named-coast-label controls that display each selected layer at every applicable anchor, independently of the configured starting state; selecting a coast label exposes its rotation control.
- **GC.23:** The `Armies` preview displays an army in every playable land territory, while the `Fleets` preview displays a fleet in every playable sea, every ordinary coastal territory and at every named anchor of a split-coast territory; delayed hover tooltips identify the home territory of every army, fleet and supply-centre marker and identify named coasts where applicable.
- **GC.24:** Placement previews do not change game state or the map's starting setup; dragging a preview unit changes only its corresponding presentation anchor.
- **GC.25:** Import initially classifies well-identified SVG elements without requiring a dedicated classification page; uncommon classification corrections remain directly editable in Definition's complete YAML source.
- **GC.26:** The topology preview draws a colour-coded adjacency graph over a faded map, using an army node and separate fleet nodes for each named coast of a split-coast territory; its key distinguishes army-only, fleet-only and shared connections, arrowheads identify asymmetric connections, and hovering a node navigates to and highlights that territory's editable YAML block.
- **GC.27:** The map editor uses independently accessible Definition, Powers & start and Placement tabs with minimal page margins and a persistent `Save configured map` action; every visual map uses compact `−`, read-only current-percentage, `+` and `Fit` controls, mouse-wheel zoom and drag panning.
- **GC.28:** Placement is the authoritative preview for the fixed army and fleet symbols, their rendered scale and their anchors.
- **GC.29:** Placement label mode independently selects no labels, display names or abbreviations; a territory can be selected on the map or by name to edit its canonical name, three-letter abbreviation and multiline display name; display names and abbreviations have separate draggable positions, Enter applies a display name while Shift+Enter inserts a line break, territory and coast font sizes have separate map-wide half-point controls, and all placement layers can be hidden to inspect overlap combinations.
- **GC.30:** Placement supply-centre previews use the same star symbol and anchor treatment as normal map rendering.
- **GC.31:** Powers & start composes its preview through the normal gameplay renderer; Placement uses the same compiled colours, stripes, labels, font sizes, centres, fixed unit symbols and presentation anchors while adding only selection and dragging affordances.
- **GC.32:** Powers and setup provides map-wide controls for text, inaccessible-region, sea and unclaimed-land colours, previews those colours immediately, and renders inaccessible regions with single-direction stripes.
- **GC.33:** Placement displays a hold underline with every visible army and fleet preview; stacked `Armies` and `Fleets` side panels adjust its horizontal and vertical offset from the corresponding unit anchor, update every matching preview immediately and persist the same offsets used by gameplay rendering.
- **GC.34:** New game provides an opt-in order-finalisation control which writes `orders.require_finalisation`; it defaults off.
- **GC.35:** Reusable maps are canonical files under the source checkout's `maps/<map-id>/` directory; saving changes those files without invoking Git and preserves ancillary provenance files.
- **GC.36:** A game's complete private map can be edited with the same Definition, Powers & start and Placement controls as a reusable map; the resulting map is used to render every phase of that game.
- **GC.37:** A private game map can replace its source reusable map after confirmation or be saved as a new reusable map with a new ID and name.
- **GC.38:** Promoting a private game map copies its design, topology, regions, names, powers, colours and presentation while retaining the source reusable map's complete default starting setup rather than the game's setup or current state.

## Limitations and Restrictions

- SVG files must already contain separately identifiable territory shapes.
- Geometry-derived adjacency requires review because off-map links, split coasts, canals and unusual map boundaries can require corrections.

## External Interface / User Experience

### Everyday Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Diplomacy   [Game ▾]                              Map | Orders       │
├─────────────────────────────────────────────────────────────────────┤
│ Context and workspace-specific controls                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                         Active workspace                            │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│      [←]                  [Spring 1902 ▾]                    [→]     │
└─────────────────────────────────────────────────────────────────────┘
```

The header and season bar remain stable while the central toolbar and workspace change between Map and Orders.

### Map Workspace

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Viewing as [Gamemaster ▾]  Position | Orders  Labels [Names ▾]      │
│                                      [Preview orders on map]        │
│          View [Full map ▾] [Save current] [Copy map] [Save image]   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                            map canvas                         [− +]  │
│                                                                Fit  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

The map canvas is also the output preview.
Controls and Fog of War warnings sit outside the copied image.

### Orders Workspace

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Spring 1902                              [Resolve and advance]       │
├───────────────────────────────┬─────────────────────────────────────┤
│ Red                           │ Blue                                 │
│ A Lon - Wal                   │ F NTH - Yor                         │
│ F Edi - NTH                   │ A Dur H                             │
├───────────────────────────────┼─────────────────────────────────────┤
│ Green                         │ Yellow                        ⚠       │
│ ...                           │ ...                                 │
└───────────────────────────────┴─────────────────────────────────────┘
```

The order text itself is the edit affordance.
The plain-text field is not visible until that text is selected.

### Map Creation Flow

```text
New game
  -> Choose configured map
     or Import SVG and create map
       -> Open independent Definition, Powers & start, and Placement tabs
          -> Edit the complete definition and review effective topology
          -> Configure powers, colours and the reusable starting setup with structured fields
          -> Edit territory names and position labels, units and supply centres
       -> Validate and save the reusable map from any tab
  -> Confirm or adjust the game's starting setup
  -> Create game

Manage configured maps
  -> Open an existing reusable map
  -> Open only the independent tabs needed for this edit
     -> Edit complete YAML and review the effective topology graphically
     -> Edit powers, colours and reusable starting defaults with structured fields
     -> Edit territory names and reposition label, army, fleet and supply-centre layers
  -> Validate and save the reusable map from the current tab

Edit current game map
  -> Open the private map in Definition, Powers & start, and Placement
  -> Save the private map after the all-phases and order-validity warning
     or update the source reusable map while retaining its default setup
     or save the design as a newly identified reusable map
```

## Design Considerations

### Minimal Everyday Interface

Infrequent controls use menus, selectors or separate setup flows, keeping the everyday workspaces focused.
The Map workspace gives the map maximum area, while the Orders workspace exposes every power at once for scanning.

### Fidelity of Player Submissions

Canonical presentation retains the original text alongside its validation result and effective order.

### Image Safety

Player-perspective mistakes can reveal game information.
The selected perspective therefore remains conspicuous on screen, while warnings and application chrome remain outside the copyable map.

### Performance, Scale and Resource Impact

The interface supports arbitrary map dimensions and aspect ratios.
Rendering and copying use the selected map view and its configured output resolution.

### Security Considerations

The application runs locally.
Imported SVG and YAML are untrusted structured input and must be parsed without executing embedded scripts, external resources or active content.
Clipboard output contains only the rendered map region selected by the gamemaster.

## Open Issues and Risks

- Geometry-derived adjacency can produce false positive and false negative links, so map creation must make the generated topology and its validation status conspicuous.
- Automated placement can produce poor anchors for irregular or disconnected shapes; the Placement tab provides manual correction.
