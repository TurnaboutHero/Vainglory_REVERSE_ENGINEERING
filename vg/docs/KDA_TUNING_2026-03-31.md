# KDA Tuning 2026-03-31

## Current Best Pure `.vgr` Setting

Current best known detector setting on complete truth fixtures:

- `kill_buffer = 20`
- `death_buffer = 3`
- plus conditional late-death rescue

Current complete-fixture result:

- kills: `97 / 99`
- deaths: `96 / 99`
- assists: `96 / 99`
- combined K+D+A: `289 / 297 = 97.3064%`

## What Improved

Compared with the earlier conservative default:

- `kill_buffer` widening fixed several real scoreboard-counted late kills
- conditional late-death rescue recovered one late truth-counted death
- narrowing the base `death_buffer` back to `3s` kept the same fixture score once rescue was present
- mismatch count dropped from `16` to `8`

## Remaining Pure `.vgr` Errors

Remaining mismatches at this setting:

- kills: `2`
- deaths: `3`
- assists: `3`

Patterns:

- one confirmed late phantom kill with `victim_name = None`
- one remaining duplicate/extra kill in Finals 2
- death errors are split between extra late-tail deaths and missing late deaths
- assist errors are not improved by simple rule loosening; current assist rule still wins the rule search

## Meaning

Pure `.vgr` KDA has improved materially, but it is still not a 100% lane.

The next likely path to 100% is:

1. one more narrow kill-event rule for the remaining phantom kill
2. result-screen final-state correction as a fallback when available

## Result-Screen Fallback Coverage

The captured target replay result dump now gives a practical correction lane:

- [result_screen_kda_correction_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_kda_correction_report.json)

Current coverage on that replay:

- name-bound rows recoverable from unique KDA strings: `8 / 10`
- group-confirmable rows from KDA multiset presence: `10 / 10`
- unresolved name-bound pair: `8815_LeeJiEun`, `8815_rui`

Interpretation:

- pure `.vgr` remains the default KDA lane
- result-screen memory is now strong enough to confirm the full final KDA multiset on a captured replay
- the only remaining correction blocker on the target replay is duplicate-row binding, not missing KDA text

## Current Residual Error Set

Current remaining player-level mismatches at this setting:

- kills: `2`
- deaths: `3`
- assists: `3`
- total player mismatches: `8`

Known examples:

- late phantom kill:
  - Finals 1 `2600_IcyBang`
  - kill record exists, but `victim_name = None`
- duplicate/extra kill:
  - Finals 2 `2600_staplers`
- late-tail extra deaths:
- `2599_FengLin`
- Finals 1 `2599_123`
- Finals 2 `2599_123`

This means the remaining 2.7% is now concentrated in a very small, very specific set of replay families and end-of-match event patterns.

## Narrow Phantom-Kill Filter Check

The obvious next idea was:

- drop only `victim_name = None` kills
- only when they happen well after duration

That was tested with:

- [kda_phantom_kill_rule_research_k20_d3.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/kda_phantom_kill_rule_research_k20_d3.json)

Result:

- thresholds `+8`, `+10`, `+12`, `+15` all regress the fixture score
- best kill score under this rule family is only `96 / 99`

Why:

- the Finals 1 phantom kill is real noise
- but at least two other truth-counted late kills also lack a paired victim name in the current detector path

Meaning:

- a global `late + victim None => drop` rule is not safe
- the remaining pure `.vgr` kill errors are now replay-family-specific enough that the better path is result-screen correction, not broader detector pruning
