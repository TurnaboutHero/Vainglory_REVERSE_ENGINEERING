# Local Index Export Status 2026-03-29

## Artifacts

- [index_export_local_none.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/index_export_local_none.json)
- [index_export_local_nonfinals_minion.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/index_export_local_nonfinals_minion.json)
- [index_export_target_kda_corrected.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/index_export_target_kda_corrected.json)
- [index_export_target_kda_corrected_auto.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/index_export_target_kda_corrected_auto.json)
- [index_export_target_kda_corrected_pipeline.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/index_export_target_kda_corrected_pipeline.json)
- [result_screen_kda_correction_inventory.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/result_screen_kda_correction_inventory.json)

## Replay Pool

Local replay root:

- [vg replay](/D:/Desktop/My%20Folder/Game/VG/vg%20replay)

Current decoder_v2 batch view:

- total replays: `56`
- completeness:
  - `complete_confirmed: 53`
  - `incomplete_confirmed: 3`

## Product-Safe Export

With minion policy `none`:

- accepted minion matches: `0`
- withheld minion matches: `56`

Interpretation:

- current default-safe export still withholds minion everywhere
- player/team/hero/winner/KDA remain exportable on complete replays

## Optional Partial Export

With minion policy `nonfinals-baseline-0e`:

- accepted minion matches: `49`
- withheld minion matches: `7`

Interpretation:

- current local replay pool already supports a large optional non-Finals minion rollout
- the remaining withheld set is driven by:
  - Finals-series guard
  - incomplete replays

## Consequence

The current repo is already in this state:

- default product-safe lane:
  - minion off
- optional partial lane:
  - minion on for `49/56` local replays under `nonfinals-baseline-0e`
- optional KDA correction lane:
  - result-screen correction can now be merged into export when a replay-specific correction JSON exists

## Target Replay KDA-Corrected Export

The target replay now has a concrete corrected export sample:

- [index_export_target_kda_corrected.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/index_export_target_kda_corrected.json)
- [index_export_target_kda_corrected_auto.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/index_export_target_kda_corrected_auto.json)

Current correction summary on that sample:

- corrected matches: `1`
- corrected rows: `10`

Interpretation:

- pure `.vgr` remains the default baseline
- when a result-screen correction artifact exists, export can now carry corrected KDA rows and a per-player `kda_correction_status`
- export can now discover correction payloads recursively from a `memory_sessions` root, not just a single file or one bundle directory
- recursive discovery is deterministic because preferred correction files are selected per replay before export
- the pipeline can now emit a corrected export directly from `memory_sessions` plus replay root, without manual intermediate steps

This means the remaining blocker for broader rollout is not the whole parser anymore.
The remaining blocker is concentrated in:

- Finals/outlier minion semantics
- final result-screen / scoreboard semantics
