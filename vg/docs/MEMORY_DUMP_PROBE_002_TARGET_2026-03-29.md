# Memory Dump Probe 002 Target Replay 2026-03-29

## Status

Target replay load was visually confirmed and a full memory dump was captured from that state.

## Session

- manifest:
  - [manifest.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/manifest.json)
- injection report:
  - [inject_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/inject_report.json)
- target replay loaded dump:
  - [replay_loaded_initial.dmp](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/dumps/replay_loaded_initial.dmp)
- target replay loaded full dump:
  - [replay_loaded_initial_full.dmp](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/dumps/replay_loaded_initial_full.dmp)
- keyword reports:
  - [replay_loaded_initial_keyword_search.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_loaded_initial_keyword_search.json)
  - [replay_loaded_initial_keyword_search_v2.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_loaded_initial_keyword_search_v2.json)
  - [replay_loaded_initial_full_keyword_search.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_loaded_initial_full_keyword_search.json)

## Visual Confirmation

One replay-loaded frame clearly showed target replay player labels such as:

- `8815_DIOR`
- `8815_Sui`
- `8815_nok`
- `8815_mumu`
- `8815_Bro`
- `8815_korea`
- `8815_LeeJiEun`
- `8815_rui`
- `8815_lamy_KR`

Interpretation:

- the overwrite + replay-entry path can reach the intended target replay
- this is no longer just a theory or handoff note

## Dump Findings

Lean dump:

- did not expose the target player labels as simple strings
- still showed `Temporary` markers

Full dump:

- did expose target replay identifiers and names
- keyword hits included:
  - `8815`
  - `DIOR`
  - `korea`
  - `rui`

Interpretation:

- lean dumps are good for fast state transitions
- full dumps are currently better for extracting replay-specific participant names

## Important Consequence

This is the first strong proof that:

- replay-state memory analysis is viable
- target replay identity can be recovered from memory
- full dumps may be necessary for player-name/state recovery

## Remaining Gaps

- result-screen dump still missing
- scoreboard-open dump for target replay still missing
- replay UI after target load is still fragile
