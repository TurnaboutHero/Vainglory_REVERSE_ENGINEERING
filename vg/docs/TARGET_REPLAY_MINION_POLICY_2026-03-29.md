# Target Replay Minion Policy 2026-03-29

## Artifacts

- [target_replay_decoder_v2_debug.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/target_replay_decoder_v2_debug.json)
- [target_replay_minion_candidate_summary.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/target_replay_minion_candidate_summary.json)
- [target_replay_minion_policy_summary.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/target_replay_minion_policy_summary.json)

## Replay Status

Target replay:

- `GameMode_5v5_Ranked`
- `complete_confirmed`
- non-Finals replay

This matters because it means the conservative optional minion policy can be applied without the Finals-series guard.

## Policy Evaluation

For this replay:

- `none`
  - accepted match: `false`
  - accepted players: `0`
- `nonfinals-baseline-0e`
  - accepted match: `true`
  - accepted players: `10`
- `nonfinals-or-low-mixed-ratio-experimental`
  - accepted match: `true`
  - accepted players: `10`

## Baseline Candidate Values

Per-player baseline `0x0E` counts on this replay:

- `8815_DIOR` -> `145`
- `8815_Bro` -> `26`
- `8815_mumu` -> `11`
- `8815_nok` -> `100`
- `8815_Sui` -> `138`
- `8815_korea` -> `119`
- `8815_LeeJiEun` -> `124`
- `8815_zm` -> `19`
- `8815_rui` -> `58`
- `8815_lamy_KR` -> `6`

`0x0F` matches `0x0E` for all ten players in this replay.

## Interpretation

This replay is useful for the minion track because:

- exact player identity is already recovered from `.vgr`
- winner and K/D/A are already accepted
- the replay is not blocked by the Finals-series policy gate
- it provides a clean per-player `0x0E/0x0F/0x0D` snapshot for future validation

## Consequence

For non-Finals complete replays like this one:

- the parser/decoder path is already strong enough to export optional minion values under the current conservative policy

The remaining open problem is not this replay.
The remaining open problem is:

- Finals-series/outlier behavior
- final scoreboard/result semantics
- proving or disproving engine-side scoreboard models from memory
