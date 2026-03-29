# Memory Dump Probe 003 Live Replay HUD 2026-03-29

## Status

Live Windows-MCP automation reached the target replay again and captured improved full dumps from replay HUD states.

Artifacts:

- [live_replay_inject_latest.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/live_replay_inject_latest.json)
- [replay_loaded_hud_full.dmp](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/dumps/replay_loaded_hud_full.dmp)
- [replay_mid_hud_full.dmp](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/dumps/replay_mid_hud_full.dmp)
- [replay_loaded_hud_full_keyword_search.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/replay_loaded_hud_full_keyword_search.json)
- [replay_mid_hud_full_keyword_search.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/replay_mid_hud_full_keyword_search.json)
- [replay_mid_hud_full_keyword_audit.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/replay_mid_hud_full_keyword_audit.json)
- [player_handle_candidates_8815_loaded.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/player_handle_candidates_8815_loaded.json)
- [player_handle_candidates_8815.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_003_live/player_handle_candidates_8815.json)

## Live Automation Result

Confirmed sequence:

- home
- play
- practice
- hero select
- talent select
- build skip via `Esc`
- in-match scoreboard
- surrender overlay
- `vgrplay` overwrite
- replay entry
- target replay HUD visible

`vgrplay` overwrite succeeded again:

- changed files: `115`
- return code: `0`

## Important New Finding

Unlike the earlier `probe_002_target` full dumps, the `probe_003_live` replay HUD dumps **do** expose exact target player labels.

For both:

- `replay_loaded_hud_full.dmp`
- `replay_mid_hud_full.dmp`

exact labels were found as `utf16le`:

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

Prefix-filtered handle extraction also returns them:

- `player_handle_candidates_8815_loaded.json`
- `player_handle_candidates_8815.json`

## Interpretation

This changes the earlier memory conclusion in an important way:

- exact player labels are **not** available in every replay-related full dump
- but they **are** recoverable from full dumps once the replay HUD/player panel state is present

So the current state-dependent reading is:

- `probe_002_target`
  - replay loaded, but current captured state was still too early/noisy for clean exact labels
- `probe_003_live`
  - replay HUD with player panels visible
  - exact labels become recoverable from memory

## Remaining Gap

Even with exact player labels now visible in memory:

- clean final result-screen model is still missing
- scoreboard/result numeric panel structure is still not isolated
- Finals/outlier minion semantics are still unresolved

## Consequence

The memory track is now stronger than before:

- exact player identity from memory is possible
- but it appears to depend on the replay HUD/player-panel state being fully present

The next live target is still:

- result-screen capture
- result-screen full dump
