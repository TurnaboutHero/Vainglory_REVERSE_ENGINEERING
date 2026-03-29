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
- full dumps expose more replay-state material than lean dumps
- but raw name-fragment hits alone are not yet enough to prove exact participant identity

## Important Consequence

This is the first strong proof that:

- replay-state memory analysis is viable
- full dumps may be necessary for player-name/state recovery
- target replay overwrite + replay HUD load can be tied to a captured full-memory state

Additional observations from the full dump:

- `8815` matched directly
- `DIOR` matched directly
- `korea` matched directly
- `rui` matched directly
- several other exact names still did not match as simple strings
- exact `8815_*` label candidates remained absent under prefix-filtered extraction
- exact `8815_*` label candidates also remained absent in the current scoreboard-open full dump

Interpretation:

- the target replay identity may be partially present in full-memory state
- but not every on-screen player label is stored as one clean contiguous string
- some hits are clearly false positives from asset/locale/config tables
- exact participant recovery from raw keyword hits is still unproven

## Keyword Hit Audit

Audit artifacts:

- [replay_loaded_initial_full_keyword_audit.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_loaded_initial_full_keyword_audit.json)
- [replay_scoreboard_open_full_keyword_audit.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_002_target/replay_scoreboard_open_full_keyword_audit.json)

Strongest conclusions from the audit:

- `8815`:
  - mostly `glyph_table`
  - not currently trustworthy as a player-identity marker
- `DIOR`:
  - entirely `asset_or_table_noise`
  - current hits are false positives such as reversed `ANDROID`-family strings
- `korea`:
  - mostly `locale_table`
  - not currently trustworthy as a player-identity marker
- `rui`:
  - mostly `unknown` or `config_or_proto`
  - too noisy to use as proof of target replay identity
- `GameMode_5v5_Practice`:
  - stable `runtime_state`
  - still a useful dynamic state marker
- `Temporary`:
  - mixed `runtime_state`, `symbol_table`, and `unknown`
  - useful with caution, but not sufficient on its own

Current interpretation:

- the strongest proof of target replay load is still:
  - successful overwrite
  - visual replay HUD confirmation
- current memory-only player-name evidence is not yet clean enough to count as exact identity recovery
- prefix-filtered exact handle extraction currently finds zero `8815_*` candidates in the captured full dump

Important split:

- exact player identity is already recoverable from the `.vgr` parser for this replay
- the memory track is now mainly about scoreboard/result semantics, not basic player-name recovery

Later update:

- [MEMORY_DUMP_PROBE_003_LIVE_2026-03-29.md](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/docs/MEMORY_DUMP_PROBE_003_LIVE_2026-03-29.md)

That later probe shows exact `8815_*` labels are recoverable from memory in a better replay HUD state.

So this probe should now be read as:

- an earlier/noisier replay-memory state
- not the final word on memory-based player identity recovery

## Remaining Gaps

- result-screen dump still missing
- scoreboard-open dump for target replay still missing
- replay UI after target load is still fragile
- next structural step is to pivot from raw keyword hits to player-name neighborhood parsing
- current scoreboard-open full dump still does not yield exact `8815_*` labels or positive handle-delta windows under string-only analysis
- numeric-token diff on the same pair is dominated by config/import/ISA/shader/http noise rather than a clean scoreboard-number model
- batch profiling of the remaining unknown numeric windows currently points to packed lookup/code tables, not scoreboard rows
