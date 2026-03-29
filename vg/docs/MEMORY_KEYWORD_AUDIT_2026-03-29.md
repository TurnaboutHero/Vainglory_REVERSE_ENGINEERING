# Memory Keyword Audit 2026-03-29

## Scope

This note audits raw keyword hits inside target replay full dumps to separate real runtime-state evidence from false positives caused by asset tables, locale tables, glyph tables, and config blobs.

Artifacts:

- [replay_loaded_initial_full_keyword_audit.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_loaded_initial_full_keyword_audit.json)
- [replay_scoreboard_open_full_keyword_audit.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_scoreboard_open_full_keyword_audit.json)
- [replay_loaded_initial_full_cluster_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_loaded_initial_full_cluster_report.json)
- [replay_scoreboard_open_full_cluster_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_scoreboard_open_full_cluster_report.json)
- [replay_loaded_vs_scoreboard_cluster_diff.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_loaded_vs_scoreboard_cluster_diff.json)
- [replay_loaded_vs_scoreboard_numeric_diff.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_loaded_vs_scoreboard_numeric_diff.json)
- [unknown_window_batch_report.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/unknown_window_batch_report.json)
- [player_handle_candidates_8815.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/player_handle_candidates_8815.json)
- [player_handle_candidates_8815_scoreboard.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/player_handle_candidates_8815_scoreboard.json)

## Findings

- `8815`
  - dominated by `glyph_table`
  - current hits look like font/CID tables, not clean runtime player labels
- `DIOR`
  - dominated by `asset_or_table_noise`
  - hits come from reversed asset-table strings such as `EDIORDNA`
- `korea`
  - dominated by `locale_table`
  - hits come from country/language lists, not player labels
- `rui`
  - mostly `unknown` with some `config_or_proto`
  - still too noisy to use as proof of target player identity
- `Temporary`
  - mixed `runtime_state`, `symbol_table`, and `unknown`
  - useful as a practice/live-state marker, not as target replay identity proof
- `GameMode_5v5_Practice`
  - stable `runtime_state`
  - currently the cleanest dynamic-state marker from memory-only search

## Interpretation

Current memory-only keyword evidence is not sufficient to claim exact target replay participant recovery.

What is still strong:

- `vgrplay` overwrite success
- visual replay HUD confirmation with target names on screen
- full dump captured from that replay-loaded state

What is not yet strong:

- exact player-identity recovery from raw dump keyword hits

Important update from later live capture:

- [MEMORY_DUMP_PROBE_003_LIVE_2026-03-29.md](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/docs/MEMORY_DUMP_PROBE_003_LIVE_2026-03-29.md)
- [MEMORY_DUMP_PROBE_004_RESULT_2026-03-29.md](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/docs/MEMORY_DUMP_PROBE_004_RESULT_2026-03-29.md)

State dependence matters.

Earlier `probe_002_target` full dumps did not expose exact `8815_*` labels cleanly.
Later `probe_003_live` replay HUD dumps do expose them as `utf16le`, and prefix-filtered extraction returns the exact names.

So the current correct reading is:

- memory-only exact label recovery is possible
- but not from every replay-related dump state
- the replay HUD/player-panel state appears to be the important gate
- the result-screen state is even stronger, because exact labels and exact stat strings co-occur there

## Cluster Findings

Window-cluster summaries currently surface:

- menu/runtime definition clusters
- locale/resource clusters
- config/proto clusters

They do not currently surface a clean scoreboard-row cluster with exact replay player labels.

`replay_loaded_initial_full_cluster_report.json` and `replay_scoreboard_open_full_cluster_report.json` both show top runtime windows dominated by:

- `Kindred*` manifests
- `GameMode_*` definitions
- menu/toast/dialog strings
- locale tables

This means current full-dump string clustering is still seeing mostly engine/resource state, not a clean scoreboard row model.

`replay_loaded_vs_scoreboard_cluster_diff.json` adds the same conclusion from the diff side:

- top changed windows are dominated by:
  - `GameMode_*` definitions
  - `Kindred*` manifests
  - glyph-table to opaque-string shifts
- there are currently `0` windows with positive `handle` delta across the full window comparison

Interpretation:

- opening the current scoreboard dump does not expose a new exact player-label string cluster under the current string-based method
- scoreboard-open state is still visible in memory, but not yet as a clean row/handle model

## Numeric-Token Diff Findings

`replay_loaded_vs_scoreboard_numeric_diff.json` compares windows by growth in short numeric-like tokens.

Top changed windows are currently dominated by:

- `config_blob`
  - example: `skinKey`, `imageName`, `heroKey`
- `import_table`
  - example: `api-ms-*`, `.dll`
- `isa_table`
  - example: `Src0.*`, `grf<...>`, `arf<...>`
- `shader_codegen`
  - example: `return mat*`, `spv*`
- `http_network`
  - example: `HTTP/1.1 200 OK`, `Content-Length`, `sessionToken`

The remaining `unknown` windows are still opaque numeric/packed-string tables, not clean scoreboard rows.

`unknown_window_batch_report.json` narrows those opaque windows further:

- `226099200`
  - stride-4 repeat ratio `~0.919`
  - repeated rows like `37373727`, `36363626`, `33333324`
  - behaves like a digit/symbol lookup table, not a scoreboard row
- `226091008`
  - stride-4 repeat ratio `~0.934`
  - repeated rows like `32323223`, `31313122`, `30303021`
  - same lookup/palette-table character
- `226107392`
  - stride-4 repeat ratio `~0.916`
  - repeated rows like `3a3a3a29`, `3c3c3c2b`, `3b3b3b2a`
  - again looks like symbol-table material
- `441106432`
  - stride-4 repeat ratio `~0.553`
  - dominated by repeated `302b756b`
  - behaves like a fixed-code table rather than a scoreboard row

Interpretation:

- scoreboard-open does cause numeric-heavy memory changes
- but current string extraction sees mostly unrelated engine/resource/network/codegen state
- there is still no clean scoreboard-number row model from the captured full dumps

## Prefix-Filtered Handle Findings

The strongest target-specific test so far is:

- known on-screen replay prefix: `8815_`
- prefix-filtered candidate extraction:
  - [player_handle_candidates_8815.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/player_handle_candidates_8815.json)

Result:

- `candidate_count = 0`
- scoreboard-open dump also returns `candidate_count = 0`

Interpretation:

- the exact on-screen `8815_*` labels are not currently recoverable as contiguous string tokens from the captured full dump
- this remains true even in the current `scoreboard_open_full` capture
- replay participant identity is therefore still stronger from:
  - visual replay HUD confirmation
  - `vgrplay` overwrite evidence
than from current memory-only string extraction

## Next Step

Move from raw keyword hits to structured parsing:

- extract offset-aware string clusters around dynamic-state regions
- compare `replay_loaded_initial_full` vs `scoreboard_open_full`
- search for repeated row-like layouts instead of isolated string matches
