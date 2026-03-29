# Target Replay Decoder Summary 2026-03-29

## Replay

- [0f66f336-3e1c-11eb-ad3d-02ea73c392db-28c9273d-f413-4d68-898c-5388383873f5.0.vgr](/D:/Desktop/My%20Folder/Game/VG/vg%20replay/21.11.17/%EB%A6%AC%ED%94%8C/0f66f336-3e1c-11eb-ad3d-02ea73c392db-28c9273d-f413-4d68-898c-5388383873f5.0.vgr)
- decoder output:
  - [target_replay_decoder_v2_debug.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/target_replay_decoder_v2_debug.json)
  - [target_replay_minion_candidate_summary.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/target_replay_minion_candidate_summary.json)

## Safe Decoder Result

`decoder_v2` classifies this replay as:

- `GameMode_5v5_Ranked`
- `Sovereign Rise`
- `complete_confirmed`
- winner: `left`

Accepted from disk:

- exact player labels
- team grouping
- hero names
- winner
- K/D/A

Withheld from disk:

- minion kills
- duration as index-safe final field

## Exact Players

Left:

- `8815_DIOR` — Baron — `12 / 1 / 4`
- `8815_Bro` — Tony — `3 / 1 / 16`
- `8815_mumu` — Phinn — `1 / 1 / 21`
- `8815_nok` — Leo — `2 / 2 / 10`
- `8815_Sui` — Magnus — `14 / 1 / 8`

Right:

- `8815_korea` — Vox — `0 / 9 / 3`
- `8815_LeeJiEun` — Ringo — `2 / 5 / 2`
- `8815_zm` — Fortress — `2 / 6 / 2`
- `8815_rui` — Grace — `2 / 5 / 2`
- `8815_lamy_KR` — Ardan — `0 / 7 / 3`

## Minion Candidate Snapshot

This replay does produce per-player minion candidate signals.

Examples:

- `8815_DIOR`
  - `action_0e_value_1 = 145`
  - `action_0f_value_1 = 145`
  - `action_0d_total = 41`
- `8815_Bro`
  - `action_0e_value_1 = 26`
  - `action_0f_value_1 = 26`
  - `action_0d_total = 35`
- `8815_LeeJiEun`
  - `action_0e_value_1 = 124`
  - `action_0f_value_1 = 124`
  - `action_0d_total = 10`

Interpretation:

- this is a useful non-Finals target replay for future minion validation
- it already has exact player identity from `.vgr`
- it also has per-player `0x0E/0x0F/0x0D` candidate traces

## Consequence

This replay is a good bridge case between the parser track and the memory track:

- parser track:
  - already exact for player/team/hero/winner/KDA
- memory track:
  - still needed only if we want to recover final scoreboard/result/minion semantics from engine state
