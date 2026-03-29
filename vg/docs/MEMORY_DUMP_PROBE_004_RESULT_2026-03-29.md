# Memory Dump Probe 004 Result Screen 2026-03-29

## Status

The replay finally reached the result screen, and a full dump was captured from the final scoreboard state.

Artifacts:

- [result_screen_full.dmp](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/dumps/result_screen_full.dmp)
- [result_screen_desktop.png](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_desktop.png)
- [result_screen_full_keyword_search.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_full_keyword_search.json)
- [result_screen_handle_candidates_8815.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_handle_candidates_8815.json)
- [result_neighborhood_8815_DIOR.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_neighborhood_8815_DIOR.json)
- [result_neighborhood_12_1_4.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_neighborhood_12_1_4.json)
- [result_neighborhood_13_8k.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_neighborhood_13_8k.json)
- [result_screen_row_probe.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_row_probe.json)
- [result_screen_full_cluster_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/result_screen_full_cluster_report.json)

## Visible Final Screen

The result screen visibly showed:

- team score: `32` vs `6`
- victory label: `승리`
- exact player labels
- per-player K/D/A
- per-player gold like `13.8k`
- per-player final minion values like `145`

## Keyword Search Result

Exact player labels were found in `utf16le`:

- `8815_DIOR`
- `8815_Sui`
- `8815_nok`
- `8815_mumu`
- `8815_Bro`
- `8815_korea`
- `8815_LeeJiEun`
- `8815_rui`
- `8815_lamy_KR`
- `8815_zm`

Exact stat strings were also found in `utf16le`:

- `12/1/4`
- `14/1/8`
- `3/1/16`
- `0/9/3`
- `13.8k`
- `145`
- `승리`

## Important Neighborhood Finding

The `8815_DIOR` neighborhoods now show row-like result data nearby.

Examples visible around `8815_DIOR`:

- `12/1/4`
- `13.8k`
- `145`

Interpretation:

- the result screen does not just expose the player names
- it exposes at least some final row values close enough in memory to treat this as a real scoreboard/result-state candidate

## Row-Probe Status

`result_screen_row_probe.json` shows:

- exact player labels are recoverable
- exact KDA/gold/minion strings are recoverable
- but stable `name -> stats` row binding is still only partial with the current neighborhood method

Current correlation signal:

- `8815_rui` with `2/5/2` co-occurs within a moderate radius
- wider-radius checks start to recover a few more name/KDA pairs
- but it is not yet a clean systematic extractor for all 10 players

Interpretation:

- result-screen data is definitely in memory
- a first-generation row probe exists
- the remaining work is structural row extraction, not basic presence/absence

## Meaning

This is a major step forward compared with earlier probes:

- `probe_002_target`
  - target replay loaded, but memory evidence was noisy
- `probe_003_live`
  - replay HUD exact names became recoverable
- `probe_004_result`
  - final result screen exposes exact player names plus exact stat strings in memory

## Remaining Gap

What is still missing is not whether the result screen exists in memory.

What is still missing is:

- a systematic extractor that maps:
  - player label
  - K/D/A
  - gold
  - minion
  - team/winner
into one stable parsed row model

## Consequence

The memory track now has a clear target:

- build a result-screen row extractor around the exact-name neighborhoods

This is now much more promising than the earlier replay-HUD-only string search.
