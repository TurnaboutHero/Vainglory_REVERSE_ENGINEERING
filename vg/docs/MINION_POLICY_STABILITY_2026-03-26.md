# Minion Policy Stability 2026-03-26

Source:
- [decoder_v2_minion_policy_stability_audit.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/decoder_v2_minion_policy_stability_audit.json)

## Purpose

This audit is not about searching for new rules.

It checks the fixed policies that actually exist in code and shows:

- where they abstain
- where they are correct
- where they fail

## Fixed Policies

### `none`

- complete-only coverage: `0.0`
- complete-only precision: `0.0`

Interpretation:

- safe default
- no minion export

### `nonfinals-baseline-0e`

- complete-only accepted rows: `40 / 78`
- complete-only precision: `1.0`
- complete-only coverage: `0.5128`
- finals accepted rows: `0`

Interpretation:

- the current product-facing optional policy is clean
- it simply abstains on Finals

### `nonfinals-or-low-mixed-ratio-experimental`

- complete-only accepted rows: `49 / 78`
- complete-only precision: `0.9796`
- complete-only coverage: `0.6282`
- finals accepted rows: `9`
- finals accepted errors: `1`

Interpretation:

- the current experimental policy does add real coverage
- but it is still not fully safe

## Error Concentration

The experimental policy error is concentrated, not diffuse.

Current wrong accepted row:

- series: `SFC vs Law Enforcers (Finals)`
- replay: `Finals 2`
- player: `2599_123`
- baseline `0x0E`: `7`
- truth minion kills: `6`
- mixed ratio: `0.0`
- error: `+1`

Interpretation:

- this is a good sign operationally because the error is localized
- it is still not good enough for default export

## Replay Shape

`nonfinals-baseline-0e`

- all Semis rows: accepted and exact
- all Maitun rows: accepted and exact
- all Finals rows: withheld

`experimental`

- many Finals rows remain withheld
- accepted Finals rows are mostly exact
- the one known mistake sits in `Finals 2`

## Decision

Current policy split remains correct:

- default: `none`
- product-facing optional: `nonfinals-baseline-0e`
- research/ops only: `nonfinals-or-low-mixed-ratio-experimental`

## Why This Matters

The search report and cross-validation report answer:

- can we find better-looking rules?
- do those rules generalize?

This stability audit answers a different question:

- given the fixed policies we actually expose, what happens per series and per replay?

Right now that answer supports the current product stance without change.
