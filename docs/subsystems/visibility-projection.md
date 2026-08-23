# Visibility Projection

## Responsibility

Visibility Projection converts complete phase information into a perspective-safe rendering input.
It is the sole authority for deciding which state and order information crosses into restricted views.

## External API

The subsystem provides `VisibilityProjector` from [Subsystem API Contracts](../api-contracts.md).
`project` consumes a map, phase, effective orders, policy and projection request and returns `ProjectedMapState`.

## Implementation Notes

The implementation is a stateless transformation over immutable inputs.
It calculates visible territory identifiers from the selected power's active and dislodged unit locations over the union of army and fleet territory connections, including exceptional and off-map links.
It then constructs either `VisibleTerritory` or `HiddenTerritory` for every playable territory.

Order and result projection is performed after territory visibility is known.
Any retained order graphic is rebuilt from permitted fields, ensuring that hidden locations cannot remain embedded in support, convoy or tooltip data.
The gamemaster path uses the same construction with every territory visible.

## Modules

- `policy` evaluates `VisibilityPolicy` against unit locations and map topology to produce the visible territory set.
- `projector` implements `VisibilityProjector` and constructs the discriminated visible or hidden territory records.
- `order_filter` retains only orders and results whose complete rendered representation is permitted by the visible set and preserves the validity needed by order styling.

`order_filter` creates new values field by field instead of copying source objects and then removing selected fields.
This construction makes accidental retention of hidden support or convoy references testable at the contract boundary.

## Dependencies

- Shared map, game, order and projection contracts.
- No renderer or persistence dependency.
