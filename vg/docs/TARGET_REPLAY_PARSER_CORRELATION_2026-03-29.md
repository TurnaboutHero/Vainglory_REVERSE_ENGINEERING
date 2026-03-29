# Target Replay Parser Correlation 2026-03-29

## Scope

This note separates two questions that were getting conflated:

1. Can the on-disk `.vgr` replay parser recover the target replay players and match summary?
2. Can the current memory-dump string analysis recover the same identity directly from engine memory?

These do not currently have the same answer.

Artifacts:

- [target_replay_decoder_v2_debug.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/target_replay_decoder_v2_debug.json)

## Parser Result

For replay:

- `0f66f336-3e1c-11eb-ad3d-02ea73c392db-28c9273d-f413-4d68-898c-5388383873f5.0.vgr`

`decoder_v2` already recovers the exact player labels and teams from disk:

- left:
  - `8815_DIOR`
  - `8815_Bro`
  - `8815_mumu`
  - `8815_nok`
  - `8815_Sui`
- right:
  - `8815_korea`
  - `8815_LeeJiEun`
  - `8815_zm`
  - `8815_rui`
  - `8815_lamy_KR`

It also recovers:

- game mode: `GameMode_5v5_Ranked`
- map: `Sovereign Rise`
- completeness: `complete_confirmed`
- winner: `left`
- K/D/A: accepted
- duration estimate: `1136s` from crystal

## Interpretation

Current parser/decoder already gives exact player identity for this replay from the `.vgr` data itself.

The memory-dump track is therefore **not** needed for basic player/team identity on this replay.

The memory-dump track remains useful for a different question:

- whether final scoreboard/result state exists in a clean engine/UI model that can explain fields that are still partial from `.vgr`, especially:
  - minion kills
  - final scoreboard/result state
  - possibly exact duration/result presentation

## Current Split

Strong from `.vgr`:

- player labels
- hero ids / hero names
- team grouping
- winner on complete replay
- K/D/A on complete replay

Not yet strong from memory-only string extraction:

- exact player-label recovery from captured full dumps
- clean scoreboard row model
- final result-screen data model

## Consequence

The most productive use of the memory track is now:

- scoreboard/result semantics
- final numeric panel state
- minion/result-side UI model

not re-proving player identity that the `.vgr` parser already recovers exactly.
