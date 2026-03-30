# Result Screen Row Linking 2026-03-29

## Artifacts

- [result_screen_va_locator_fullset.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_va_locator_fullset.json)
- [result_screen_cluster_candidates.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_cluster_candidates.json)
- [result_screen_cluster_assignment_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_cluster_assignment_report.json)
- [result_screen_kda_correction_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_kda_correction_report.json)
- [result_screen_row_anchor_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_row_anchor_report.json)
- [result_screen_row_anchor_sweep.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_row_anchor_sweep.json)

## Current Best Candidate

Best current result-screen cluster:

- VA range: `0x46166948 -> 0x46167530`
- score: `108.09375`

Contained names:

- `8815_Bro`
- `8815_Sui`
- `8815_nok`
- `8815_rui`
- `8815_zm`

Contained KDA strings:

- `3/1/16`
- `14/1/8`
- `2/2/10`
- `2/5/2`
- `2/6/2`
- plus extra nearby KDA strings from adjacent rows/caches

Contained gold strings:

- `10.1k`
- `11.3k`
- `12.7k`
- `13.8k`

## What Can Already Be Reconstructed

From this one cluster alone:

- KDA can already be matched automatically for `5` players:
  - `8815_Bro`
  - `8815_Sui`
  - `8815_nok`
  - `8815_rui`
  - `8815_zm`
- Gold can already be matched automatically for `2` players:
  - `8815_Sui` -> `12.7k`
  - `8815_nok` -> `10.1k`

This is not yet a full result extractor, but it is no longer a pure presence-only result.

## Current Limitation

The remaining five players are not yet linked cleanly by the same cluster logic:

- `8815_DIOR`
- `8815_mumu`
- `8815_korea`
- `8815_LeeJiEun`
- `8815_lamy_KR`

What blocks them now:

- names, KDA strings, and gold strings are split across multiple nearby VA clusters
- some clusters are mixed caches rather than one clean row table
- duplicate KDA values like `2/5/2` create ambiguity without stronger row structure

## Anchor Sweep

`result_screen_row_anchor_sweep.json` shows the current first-pass anchor method is still weak:

- at `1024` bytes: `1` KDA hit, `0` gold hits
- at `2048` bytes: `1` KDA hit, `0` gold hits
- at `4096` bytes: `1` KDA hit, `0` gold hits
- larger radii do not materially improve this

Interpretation:

- naive `nearest name -> nearest stat` is not enough
- cluster-aware linking is better than direct nearest-neighbor linking

## Current State

The result-screen track has now progressed to:

- exact names present in memory
- exact KDA/gold/minion strings present in memory
- first useful mixed cluster found
- partial automatic row reconstruction working for a subset
- full KDA multiset confirmation on the captured replay

Current correction coverage:

- name-bound KDA reconstruction: `8 / 10`
- group-confirmable KDA rows: `10 / 10`
- only unresolved duplicate group: `8815_LeeJiEun` / `8815_rui` with shared `2/5/2`

The remaining task is:

- merge multiple VA clusters into one stable 10-player result model
