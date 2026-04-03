# Result Screen KDA Correction 2026-03-31

## Artifact

- [result_screen_kda_correction_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_kda_correction_report.json)
- [result_screen_kda_correction_apply.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_kda_correction_apply.json)
- [target_replay_corrected_kda_rows.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/target_replay_corrected_kda_rows.json)

## What It Measures

The correction report separates two levels of confidence:

- `name-bound`
  - a player name can be tied directly to its final KDA because that KDA string is unique in the match
- `group-confirmable`
  - the final result dump confirms that a KDA string exists for an expected duplicate group, even if the exact duplicate rows are not yet separated from each other

## Current Target Replay Result

For the captured target replay result dump:

- total rows: `10`
- name-bound reconstructable rows: `8`
- group-confirmable rows: `10`
- duplicate-group rows: `2`
- unresolved name-bound rows:
  - `8815_LeeJiEun`
  - `8815_rui`

## Meaning

This is enough to say:

- result-screen memory already contains the full final KDA multiset for the target replay
- the remaining gap is not missing KDA data
- the remaining gap is duplicate-row binding for one shared `2/5/2` pair

## Why This Matters

For KDA accuracy work, this changes the problem shape:

- pure `.vgr` tuning has reached `289 / 297 = 97.3064%`
- result-screen correction is no longer blocked by data absence
- it is blocked only by stable row-linking for duplicate KDA groups

That makes the next useful task narrower:

- keep `.vgr` as the default KDA lane
- use result-screen correction where a final result dump exists
- finish duplicate-row binding rather than continuing broad heuristic tuning

## First Apply Pass

The current apply lane can already assign corrected KDA values to all `10 / 10` rows on the target replay:

- `8` rows are `name_bound_unique`
- `2` rows are `group_confirmed_duplicate`

This works because the unresolved duplicate pair shares the same final KDA value:

- `8815_LeeJiEun` -> `2/5/2`
- `8815_rui` -> `2/5/2`

So the remaining gap is not KDA application on the captured replay.
The remaining gap is making the same duplicate-group logic robust across more replays.

## Merge Step

The correction lane now also supports a direct merge step back into decoded player rows.

That means the current target replay can produce:

- parser baseline rows
- result-screen correction statuses
- merged corrected player rows

without manual editing of the final player table.

## Bundle Step

The report/apply/merge flow is now also available as a one-shot bundle builder:

- [result_screen_kda_correction_bundle.py](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/tools/result_screen_kda_correction_bundle.py)
- [result_screen_kda_correction_autobundle.py](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/tools/result_screen_kda_correction_autobundle.py)

Inputs:

- one decoded replay JSON
- one result-screen full dump

Outputs:

- `result_screen_kda_correction_report.json`
- `result_screen_kda_correction_apply.json`
- `result_screen_kda_correction_merge.json`

This reduces the manual integration cost for future captured replays.

`autobundle` goes one step further:

- read `replay_name` from `manifest.json` when present
- find the matching decoded debug JSON under an output root
- locate `result_screen_full.dmp`
- emit bundle artifacts without manually naming the decoded payload file

## Recursive Discovery

The export lane now supports recursive correction discovery from a whole memory-session root.

Current supporting artifacts:

- [result_screen_kda_correction_inventory.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/result_screen_kda_correction_inventory.json)
- [index_export_target_kda_corrected_auto.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/index_export_target_kda_corrected_auto.json)
- [result_screen_kda_correction_pipeline.py](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/tools/result_screen_kda_correction_pipeline.py)
- [result_screen_kda_correction_readiness.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/result_screen_kda_correction_readiness.json)
- [result_screen_kda_validation.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/result_screen_kda_validation.json)
- [kda_result_capture_backlog.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/kda_result_capture_backlog.json)

Selection policy:

- prefer `result_screen_kda_correction_merge.json`
- then prefer standalone corrected-row payloads
- then prefer higher `corrected_rows`
- then prefer lower `unresolved_rows`

This makes `--kda-correction-path <memory_sessions_root>` deterministic even when multiple correction files exist.

## Pipeline Step

There is now a top-level pipeline that can:

- scan a memory-session root for sessions containing `result_screen_full.dmp`
- autobundle each session
- rebuild correction inventory
- optionally emit a corrected export in one run

That closes most of the remaining manual glue between:

- captured result-screen dump
- correction artifacts
- final export

## Readiness / Validation / Backlog

The correction lane now emits three operational views:

- `readiness`
  - one replay-level status row per discovered replay or decoded-only replay
  - identifies whether the next step is dump capture, autobundle, inventory, corrected export, or review
- `validation`
  - compares parser baseline vs corrected rows against either truth or result-screen reference rows
- `capture backlog`
  - prioritizes the next replay captures, with truth residual replays first

This means the next action is no longer “inspect the folder and guess”.
The next action is “read the backlog and capture the top replay”.
