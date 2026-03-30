# KDA Team Ceremony Audit 2026-03-26

Source of truth:
- [decoder_v2_kda_postgame_audit.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/decoder_v2_kda_postgame_audit.json)
- [tournament_truth.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/tournament_truth.json)

## Scope

This audit answers two product questions:

1. Is team grouping stable enough for index export?
2. Are post-match ceremony kills/deaths leaking into K/D/A?

## Team Grouping

Current status: strong enough for product use.

- player-block records validated: `110`
- nonzero entity ids: `110`
- team bytes seen: `{1: 55, 2: 55}`
- direct hero matches from player block: `109 / 109`

Interpretation:
- binary team grouping from player block `+0xD5` is stable
- screenshot-side swap is a presentation issue, not a binary team-grouping issue

## Post-Game Tail

Raw late events still exist in truth-covered fixtures.

- kills after truth duration: `5`
- kills more than `+3s`: `5`
- kills more than `+10s`: `3`
- deaths after truth duration: `15`
- deaths more than `+3s`: `11`
- deaths more than `+10s`: `9`

Important examples:

- [SFC vs Team Stooopid (Semi) / 2](/D:/Desktop/My%20Folder/Game/VG/vg%20replay/Tournament_Replays/SFC%20vs%20Team%20Stooopid%20(Semi)/2)
  - late death at `+2.188s`
- [SFC vs Maitun Gaming / 1](/D:/Desktop/My%20Folder/Game/VG/vg%20replay/Tournament_Replays/SFC%20vs%20Maitun%20Gaming/1)
  - late kill at `+6.158s`
  - late death at `+7.998s`
- [Buffalo vs RRONE / 2](/D:/Desktop/My%20Folder/Game/VG/vg%20replay/Tournament_Replays/Buffalo%20vs%20RRONE/2)
  - late kill at `+3.741s`
  - late deaths at `+0.569s`, `+0.617s`, `+1.677s`, `+5.515s`

Interpretation:
- some late events are obvious ceremony noise
- some short-tail late deaths look like real scoreboard-counted deaths that land just after the nominal match duration

## Buffer Comparison

Using raw `KDADetector` against truth durations:

| config | complete-only kills | complete-only deaths | complete-only assists | combined |
|---|---:|---:|---:|---:|
| `kill=0, death=0` | `94 / 99` | `91 / 99` | `91 / 99` | `276 / 297` |
| `kill=3, death=0` | `94 / 99` | `91 / 99` | `91 / 99` | `276 / 297` |
| `kill=3, death=10` | `94 / 99` | `95 / 99` | `91 / 99` | `280 / 297` |
| `kill=5, death=10` | `95 / 99` | `95 / 99` | `92 / 99` | `282 / 297` |
| `kill=20, death=3` | `97 / 99` | `96 / 99` | `96 / 99` | `289 / 297` |
| `kill=20, death=8` | `97 / 99` | `96 / 99` | `96 / 99` | `289 / 297` |

What this means:

- `death_buffer=0` is too strict on current fixtures
- `death_buffer=3` performs as well as wider rescue-based settings on current fixtures
- current fixture set contains real scoreboard-counted kills beyond `+3s`
- widening `kill_buffer` materially improves kills and assists on complete fixtures
- current best known fixture-backed setting is `kill_buffer=20`, `death_buffer=3`
- the current detector also uses a conditional late-death rescue:
  - keep very-late deaths only when they align closely with an opposing late kill

## Product Position

Current recommendation:

- team grouping: accepted
- K/D/A on complete-confirmed replays: accepted
- use `kill_buffer=20`
- use `death_buffer=3`

Rationale:

- team grouping is already strong from direct offsets
- strict `death_buffer=0` makes fixture agreement worse
- raw late events exist, but several of them are clearly reflected on the final result boards
- `kill_buffer=20`, `death_buffer=3` plus conditional late-death rescue reduces complete-fixture player mismatches from `16` to `8`

## Follow-up

- if more truth becomes available, rerun this audit before changing K/D/A default buffers
- if a cleaner exact end-of-match signal is found, re-evaluate `kill_buffer` and `death_buffer` together
