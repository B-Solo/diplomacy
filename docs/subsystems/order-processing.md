# Order Processing

## Responsibility

Order Processing converts player-supplied text into preserved, canonical and rule-validated submission records.
It owns language tolerance and formatting while the Rules Engine owns legality.

## External API

The subsystem provides `OrderProcessor` from [Subsystem API Contracts](../api-contracts.md).
`interpret` parses source lines into candidates, and `prepare_submission` combines recognised candidates with `RulesEngine.validate` results.

## Implementation Notes

Parsing is line-oriented so every issue and engine result can be traced back to the original text.
Territory resolution uses a case-insensitive index of canonical names and abbreviations from `MapDefinition`; canonical output uses configured territory abbreviations while the original submitted text remains unchanged.
Move parsing accepts `-`, `->` or `to` separators and resolves multi-word names on either side before tokenising the remaining order grammar.

The parser produces a typed order syntax tree before rule validation without rewriting the source text stored alongside it.
It reports textual ambiguity and missing structure but does not inspect adjacency, unit ownership or phase legality.
Unrecognised lines survive unchanged, while recognised invalid orders retain the effective order returned by the Rules Engine.
Adjustment parsing accepts an explicit `Waive` order, which canonicalises without a unit or map location.

The subsystem is stateless apart from immutable lookup indexes that may be cached by `MapId`.

## Modules

- `service` implements `OrderProcessor` and combines parsing with Rules Engine validation.
- `lexer` divides multiline input into source-preserving tokens and ignores only insignificant whitespace.
- `parser` constructs typed order candidates and syntax issues without applying board rules.
- `map_names` builds case-insensitive canonical-name and abbreviation indexes and reports ambiguous matches.
- `canonicaliser` renders recognised orders using the application's phase-appropriate canonical notation.
- `submission_builder` aligns parser and validation results by source line and always clears finalisation after an edit.

Parser recovery is confined to the current line so one malformed order cannot consume or alter following orders.

## Dependencies

- `RulesEngine` for rule validation.
- Shared map and order contracts.
