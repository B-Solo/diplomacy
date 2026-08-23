# Map Rendering

## Responsibility

Map Rendering creates a self-contained SVG scene from a configured map and projected state, then exports bounded PNG images.
It owns visual composition and order geometry while treating its input as already authorised for disclosure.

## External API

The subsystem provides `MapRenderer` from [Subsystem API Contracts](../api-contracts.md).
`compose` returns a `MapScene`, and `export` rasterises the requested map bounds into an `ImageArtifact`.

## Implementation Notes

Composition clones the sanitised base SVG and adds deterministic layers for territory fills, labels, supply-centre stars, units and orders.
All coordinates use the source SVG view box so maps of different dimensions and aspect ratios follow the same pipeline.
In retreat phases, a dislodged unit remains at its origin with an `R` marker and is offset when an active unit occupies the same territory.
When projected adjudication explanations are present, composition returns map-coordinate hit paths alongside the SVG so the UI can implement order hover without parsing rendered content.

Move paths are constructed before dependent support and convoy graphics.
Support-to-move paths terminate on the computed move path; convoy connectors use a pronounced wave and terminate on the convoyed move path.
A convoyed move may use a smoothed representative path through the ordered convoy fleet chain, selected deterministically from topology when several chains exist.

Export intersects requested bounds with the source map bounds before rasterisation.
Unit and order strokes use map-space sizing rules with sensible screen-space limits so zooming does not recreate oversized graphics.

## Modules

- `renderer` implements `MapRenderer` and coordinates deterministic SVG composition and projected hover hotspots.
- `territory_layers` applies controller fills, labels and supply-centre ownership stars from projected territory values.
- `unit_layers` places active and dislodged army or fleet symbols with power-derived fill, outline colours, retreat markers and collision offsets.
- `order_geometry` calculates move paths and the support, convoy, hold, invalid-movement, build and disband conventions that depend on them, including dotted effective holds for invalid movement orders.
- `svg_scene` assembles sanitised base content and generated layers into a self-contained `MapScene`.
- `raster_export` clips requested bounds and encodes a PNG at the requested output dimensions.

Layer modules return SVG fragments and geometry values rather than mutating a shared document.
Stable ordering by territory, power and source line makes identical inputs produce byte-stable scene output where the encoder permits it.

## Dependencies

- PySide6 Qt SVG, Qt GUI painting and image encoding.
- Shared map, projection and rendering contracts.
