# Minion Policy Search 2026-03-26

Source:
- [decoder_v2_minion_policy_candidates.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/decoder_v2_minion_policy_candidates.json)
- [decoder_v2_minion_policy_nonfinals_validation.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/decoder_v2_minion_policy_nonfinals_validation.json)
- [decoder_v2_minion_policy_experimental_validation.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/decoder_v2_minion_policy_experimental_validation.json)

## Goal

Search for optional partial minion-export policies that improve coverage without lowering trust.

## Current Product Recommendation

Recommended policy ordering:

1. `accept_nonfinals_only`
2. `nonfinals_or_mixed_ratio<=0.13513513513513514`

Interpretation:

- `accept_nonfinals_only` is still the best product-facing candidate
- `nonfinals_or_mixed_ratio<=0.13513513513513514` remains the best simple experimental candidate
- default decoder policy should still stay `none`

## Validation Anchors

Known validated policies:

| policy | precision | coverage | notes |
|---|---:|---:|---|
| `none` | `0.0` | `0.0` | safe default, no minion export |
| `nonfinals-baseline-0e` | `1.0` | `0.5128` | current best product-facing optional policy |
| `nonfinals-or-low-mixed-ratio-experimental` | `0.9796` | `0.6282` | useful experimental policy, but still has one wrong accepted finals row |

The single accepted error in the current experimental policy is:

- Finals 2
- player `2599_123`
- baseline `7`
- truth `6`
- mixed ratio `0.0`

## Raw Search Result

After extending candidate search with `baseline_0e` floors, raw leaderboard now finds policies with:

- `precision = 1.0`
- `coverage = 0.6282`

Examples:

- `nonfinals_or_solo_ratio<=2.3511904761904763_and_baseline_0e>=144`
- `nonfinals_or_mixed_ratio<=0.6968325791855203_and_baseline_0e>=137`

These policies are not recommended for product use.

## Why These Raw Winners Are Dangerous

They are high-complexity and almost certainly overfit.

Symptoms:

- they depend on exact floating thresholds from the current tournament set
- they require high `baseline_0e` floors like `>=137` or `>=144`
- they selectively accept a handful of finals carry rows while dropping low-CS finals rows
- they do not come from a semantic understanding of `0x02`; they come from fixture-specific separation

That makes them research artifacts, not deployable policies.

## Ranking Split

The candidate report now exposes two views:

- `top_policies`
  - raw leaderboard by precision/coverage
  - useful for research
- `recommended_policies`
  - complexity-aware ordering
  - useful for product decisions

Current expectation:

- raw leaderboard may show high-coverage precision-1.0 research-only rules
- recommended leaderboard keeps `accept_nonfinals_only` first

## Cross-Validation Check

Cross-validation now confirms that the new raw winners are overfit.

See:
- [MINION_POLICY_CROSS_VALIDATION_2026-03-26.md](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/docs/MINION_POLICY_CROSS_VALIDATION_2026-03-26.md)

Most important failure:

- in leave-one-replay-out, holding out `Finals 2`
- a training-perfect rule (`nonfinals_or_solo_ratio<=3.563953488372093`)
- drops to holdout precision `0.125`

Meaning:

- the raw `precision 1.0` leaderboard is not enough
- replay-family drift is still strong
- floor-based hybrid rules must stay research-only

## Decision

Do not promote the new floor-based rules into `minion_policy.py` yet.

Use them only as evidence that:

- the remaining accepted error is structurally removable
- but the currently removable form is overfit

So the product stance remains:

- default: `none`
- optional product-facing: `nonfinals-baseline-0e`
- optional research/ops: `nonfinals-or-low-mixed-ratio-experimental`
