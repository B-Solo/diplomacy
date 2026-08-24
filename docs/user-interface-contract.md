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
- **AN.11:** The current game's choices provide a placement-only editor for its private map snapshot.
- **AN.12:** Interactive controls and their normal, selected, hovered and disabled states maintain explicit foreground/background contrast rather than relying on the desktop theme.

### Season Navigation (SN)

- **SN.1:** The application opens at the newest season for which a state exists.
- **SN.2:** A compact previous button, season selector and next button navigate history.
- **SN.3:** Season labels contain only the season and year, for example `Spring 1901` or `Year End 1901`.
- **SN.4:** The history includes Spring, Summer, Fall, Winter and Year End for every year, including retreat or build seasons in which no orders are required.
- **SN.5:** The latest season is visibly marked `Current`.
- **SN.6:** Historical orders are visible but read-only.

### Map Workspace (MW)

- **MW.1:** The map occupies the available workspace while preserving the SVG view box and aspect ratio; surrounding chrome uses compact controls, minimal margins and overlays instead of persistent map-reducing status rows.
- **MW.2:** Loading a map fits the entire map into the workspace without stretching it; later state refreshes preserve the user's viewport.
- **MW.3:** The gamemaster zooms with a mouse wheel, a trackpad pinch or visible controls, pans by dragging, and pans vertically or horizontally with two-finger trackpad scrolling.
- **MW.4:** Mouse-wheel zoom is centred on the pointer.
- **MW.5:** Compact `−`, editable current-percentage, `+` and `Fit` controls overlay the map; wheel and button zoom use the same discrete levels.
- **MW.6:** Entering a whole percentage from `8%` to `1200%` applies that exact zoom level; `Fit` returns to the full-map view.
- **MW.7:** Pan is clamped to the map bounds.
- **MW.8:** The map display switches between `Position` and `Orders`.
- **MW.9:** Territory labels switch between full names and three-letter codes, never displaying both modes together; long full names use centred multiple lines broken at spaces or ampersands.
- **MW.10:** Land abbreviations have only their initial letter capitalised, while sea abbreviations are uppercase.
- **MW.11:** The Map toolbar contains a readable named-view selector with a visible dropdown indicator and full-name tooltips, plus `Save current` and `Copy map` actions.
- **MW.12:** Saving current-game map placement changes only label, army, fleet, named-coast and supply-centre anchors and named-coast label rotations; territory names, rules, topology, powers, setup and reusable-map defaults remain unchanged.

### Saved Views and Image Copying (IC)

- **IC.1:** A saved view records geographic bounds, aspect ratio and output pixel dimensions.
- **IC.2:** A saved view does not record season, Fog of War perspective, label mode or order-overlay state.
- **IC.3:** Recalling a saved view does not resize the application window.
- **IC.4:** `Full map` is a built-in saved view.
- **IC.5:** Saved views persist with the game so the same framing can be reused in later seasons.
- **IC.6:** `Copy map` copies the map exactly as currently presented, including its position or order display, territory-label mode, units and permitted Fog of War content.
- **IC.7:** The copied image excludes application controls, badges, outlines and any workspace beyond the SVG map bounds.
- **IC.8:** When a saved or current view reaches a map edge, the copied image aligns exactly with that edge rather than including padding outside it.

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

- **TR.1:** The current controller determines a playable land territory's colour; seas retain their neutral map treatment.
- **TR.2:** Successful occupation changes territorial control, while an empty territory retains its controller.
- **TR.3:** Supply-centre ownership is independent of current occupation and is represented by a star coloured for its owner.
- **TR.4:** Neutral supply centres use a neutral star.
- **TR.5:** Each map provides one reusable army symbol and one reusable fleet symbol.
- **TR.6:** All units of a type share the corresponding map symbol.
- **TR.7:** A unit symbol is filled with a slightly darker version of its power colour and has a still-darker outline.
- **TR.8:** Unit and supply-centre symbols are positioned using map-defined anchors and are included in copied images.
- **TR.9:** During a retreat phase, a dislodged unit remains visible at its original territory with a small `R` marker.
- **TR.10:** When another unit occupies that territory, the dislodged unit is offset so both units remain legible.

### Order Graphics (OG)

- **OG.1:** A move is a solid arrow from its unit to its destination.
- **OG.2:** Support for a move is a dotted curved line that joins the supported move arrow.
- **OG.3:** Support for a hold is a dotted line ending at the supported unit.
- **OG.4:** A convoy order is a pronounced wavy line from the convoying fleet to the convoyed move arrow, normally joining the portion of the route within that fleet's territory.
- **OG.5:** A convoyed move uses a smoothed piecewise arrow through the relevant convoy chain when a straight arrow would misleadingly cross land.
- **OG.6:** A hold is a ring around the unit.
- **OG.7:** An invalid movement order is displayed as a dotted hold ring because holding is its effective behaviour.
- **OG.8:** A build or disband displays the affected unit with a `+` or `−` over it.
- **OG.9:** Order graphics remain visually subordinate to the map and units.
- **OG.10:** A waived build appears in the canonical order list without a map graphic.

### Orders Workspace (OW)

- **OW.1:** The current season displays one power panel for every configured power.
- **OW.2:** Power panels use a two-column layout on wide windows and a single column on narrow windows.
- **OW.3:** A power panel normally shows the power, its `Final` state and its orders in canonical notation.
- **OW.4:** Selecting the canonical order text reveals a plain-text editor containing the player's original submission.
- **OW.5:** The editor accepts one order per line using territory names or abbreviations and tolerates reasonable differences in case and punctuation.
- **OW.6:** Leaving the editor returns the panel to canonical presentation while preserving the original submitted text separately.
- **OW.7:** Changes are saved and validated as they are entered and do not prevent the gamemaster from leaving the panel.
- **OW.8:** Editing any text clears that power's `Final` state.
- **OW.9:** Each editable power panel provides an explicit `Orders final` action.
- **OW.10:** The workspace provides an `Unfinalised only` filter.
- **OW.11:** During retreat and build seasons, powers with no legal decisions have inert `No orders required` panels and count as final.
- **OW.12:** An order issue is represented only by a warning flag until selected.
- **OW.13:** Selecting a warning flag expands the affected panel and reveals the warning.

### Order Interpretation (OI)

- **OI.1:** Canonical order display uses conventional compact Diplomacy notation.
- **OI.2:** Recognised valid orders display their canonical interpretation.
- **OI.3:** A recognised invalid order is retained with its validation reason and receives the standard phase-specific default effect.
- **OI.4:** An unrecognisable line is retained even when it cannot be associated with a unit.
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

### Adjudication and Advancement (AA)

- **AA.1:** The Orders workspace provides one `Resolve and advance` action.
- **AA.2:** When all relevant powers are final, the action adjudicates immediately without confirmation.
- **AA.3:** When one or more relevant powers are not final, the action warns the gamemaster and names those powers before allowing adjudication to continue.
- **AA.4:** Successful adjudication records the submitted orders and results, creates the next season's state, selects that season and opens the Map workspace.
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
- **GC.9:** Only playable regions require a territory name, abbreviation, topology and placement anchors.
- **GC.10:** The importer calculates initial label, army, fleet and supply-centre anchors and provides a visual Placement tab in which each anchor can be dragged independently.
- **GC.11:** Split coasts have separate fleet anchors and visible named-coast labels with independently configurable anchors and rotations.
- **GC.12:** The importer generates likely adjacency from SVG geometry and assumes that every coastal province has one continuous coast.
- **GC.13:** The generated ordinary topology is combined with explicit additions and removals, then materialised as the complete topology used for play.
- **GC.14:** The Topology tab gives the graphical adjacency preview approximately three quarters of the initial split, includes readable territory and split-coast nodes, exposes local connection overrides alongside the complete effective topology and provides inline, wrapping text search through the platform-standard Find shortcut.
- **GC.15:** The map-configuration editor supports split-coast connections, canals, off-map links, missed links and removal of incorrectly generated links through text.
- **GC.16:** The saved `map.yaml` remains directly editable outside the application.
- **GC.17:** A focused Powers and setup tab edits the starting phase, powers, colours, home and starting supply-centre ownership, initial territory control and starting units, provides the same inline YAML search and regenerates a map preview when applying those sections to the shared `map.yaml`.
- **GC.18:** A map may provide one custom army SVG and one custom fleet SVG; the default symbols are used when either is absent.
- **GC.19:** An existing reusable map can be reopened in the map-configuration editor without re-importing its SVG.
- **GC.20:** Reopening a map provides the same visual Placement tab as initial import, including independent territory-label, named-coast-label, army, fleet, split-coast fleet and supply-centre anchors.
- **GC.21:** Saving an edited reusable map changes the defaults used for games created afterwards and does not modify the private map snapshots of existing games.
- **GC.22:** The visual Placement tab provides independent `Armies`, `Fleets`, `Supply centres`, territory-label and named-coast-label controls that display each selected layer at every applicable anchor, independently of the configured starting state; selecting a coast label exposes its rotation control.
- **GC.23:** The `Armies` preview displays an army in every playable land territory, while the `Fleets` preview displays a fleet in every playable sea, every ordinary coastal territory and at every named anchor of a split-coast territory.
- **GC.24:** Placement previews do not change game state or the map's starting setup; dragging a preview unit changes only its corresponding presentation anchor.
- **GC.25:** Hovering any classified shape in the SVG regions tab identifies and selects its row; hovering or selecting a row highlights the corresponding shape on the map, and editing a playable territory name updates the map draft.
- **GC.26:** The topology preview draws a colour-coded adjacency graph over a faded map, using an army node and separate fleet nodes for each named coast of a split-coast territory; its key distinguishes army-only, fleet-only and shared connections, arrowheads identify asymmetric connections, and hovering a node navigates to and highlights that territory's editable YAML block.
- **GC.27:** The map editor uses independently accessible, non-sequential tabs with minimal page margins and a persistent `Save configured map` action, overlays compact `−`, current-percentage, `+` and `Fit` controls on every visual tab, and supports mouse-wheel and trackpad-pinch zoom plus trackpad scrolling consistently with the main map.
- **GC.28:** The Unit symbols tab displays compact previews of the effective default or custom army and fleet symbols at approximately their real map scale before saving.
- **GC.29:** Placement label mode independently selects no labels, full territory names or abbreviations; full names and abbreviations have separate draggable positions, and all placement layers can be hidden to inspect overlap combinations.
- **GC.30:** Placement supply-centre previews use the same star symbol and anchor treatment as normal map rendering.

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
│      [←]              [Spring 1902 ▾]  Current              [→]     │
└─────────────────────────────────────────────────────────────────────┘
```

The header and season bar remain stable while the central toolbar and workspace change between Map and Orders.

### Map Workspace

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Viewing as [Gamemaster ▾]  Position | Orders  Labels [Names ▾]      │
│                       View [Full map ▾] [Save current] [Copy map]    │
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
│ Spring 1902                  [Unfinalised only]  4 of 7 final        │
│                                             [Resolve and advance]    │
├───────────────────────────────┬─────────────────────────────────────┤
│ Red                     Final │ Blue                         Draft   │
│ A Lon - Wal                   │ F NTH - Yor                         │
│ F Edi - NTH                   │ A Dur H                             │
├───────────────────────────────┼─────────────────────────────────────┤
│ Green                   Draft │ Yellow                  ⚠     Draft │
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
       -> Open independent SVG regions, Topology, Powers and setup, Placement and Unit symbols tabs
          -> Classify shapes and edit territory and topology configuration as YAML
          -> Configure powers, colours and the reusable starting setup in a focused panel
          -> Position labels, army anchors, fleet anchors and supply-centre anchors
          -> Optionally provide army and fleet SVG symbols
       -> Validate and save the reusable map from any tab
  -> Confirm or adjust the game's starting setup
  -> Create game

Manage configured maps
  -> Open an existing reusable map
  -> Open only the independent tabs needed for this edit
     -> Inspect or reclassify linked territory shapes
     -> Edit YAML and review the effective topology graphically
     -> Edit powers, colours and reusable starting defaults
     -> Combine and reposition label, army, fleet and supply-centre placement layers
     -> Preview or replace the effective unit symbols
  -> Validate and save the reusable map from the current tab
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
