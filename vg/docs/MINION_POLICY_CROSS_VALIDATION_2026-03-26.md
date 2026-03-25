# Minion Policy Cross Validation 2026-03-26

Source:
- [decoder_v2_minion_policy_cross_validation.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/decoder_v2_minion_policy_cross_validation.json)
- [decoder_v2_minion_policy_candidates.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/decoder_v2_minion_policy_candidates.json)

## Question

Do the new `precision 1.0` raw policy candidates actually generalize, or are they just fitting the current tournament truth set?

## Result

They are overfit.

## Fixed Policy Reference

The fixed policies currently exposed by the code still behave as expected.

| policy | precision | coverage | finals accepted | finals errors |
|---|---:|---:|---:|---:|
| `accept_nonfinals_only` | `1.0` | `0.5128` | `0` | `0` |
| `nonfinals_or_mixed_ratio<=0.135135...` | `0.9796` | `0.6282` | `9` | `1` |

Interpretation:

- the conservative product candidate is still clean
- the simple experimental candidate is still useful but not fully safe

## Leave-One-Series-Out

Summary:

- folds: `3`
- mean test precision: `0.6667`
- mean test coverage: `0.6667`
- failed folds: `1`

Critical fold:

- held series: `SFC vs Law Enforcers (Finals)`
- best training policy: `accept_nonfinals_only`
- test precision: `0.0`
- test coverage: `0.0`

Interpretation:

- if Finals is held out entirely, the training set never learns a safe Finals acceptance rule
- this is expected and reinforces that Finals behavior is the unstable part of the space

## Leave-One-Replay-Out

Summary:

- folds: `8`
- mean test precision: `0.8906`
- mean test coverage: `0.7139`
- failed folds: `1`

Critical failure:

- held replay: `Finals 2`
- best training policy: `nonfinals_or_solo_ratio<=3.563953488372093`
- training precision: `1.0`
- training coverage: `0.9855`
- holdout precision: `0.125`
- holdout coverage: `0.8889`

Interpretation:

- the flashy high-coverage rule collapses exactly on the replay family we care about most
- this is direct evidence that the raw precision-1.0 leaderboard is not trustworthy for product policy selection

## What Survives

What survives this audit is not a new default rule.

What survives is the decision framework:

- keep `accept_nonfinals_only` as the first product-facing optional policy
- keep `nonfinals_or_mixed_ratio<=0.135135...` as the simple experimental policy
- keep all floor-based or solo-ratio floor hybrids in research only

## Product Decision

No change to current product stance:

- default: `none`
- optional product-facing: `nonfinals-baseline-0e`
- experimental only: `nonfinals-or-low-mixed-ratio-experimental`

## Practical Meaning

The new cross-validation tool does not prove a better minion rule.

It proves something more important:

- the tempting higher-coverage rules are not stable enough
- they fail exactly where replay-family drift is strongest
- so the cautious policy split is still correct
