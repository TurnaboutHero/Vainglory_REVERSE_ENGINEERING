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

What this means:

- `death_buffer=0` is too strict on current fixtures
- current default `death_buffer=10` is defensible because it preserves short-tail deaths that truth still counts
- current default `kill_buffer=3` is conservative and excludes all known late kills beyond `+3s`
- a wider `kill_buffer=5` improves this raw audit slightly, but it also weakens the anti-ceremony posture, so it should stay research-only for now

## Product Position

Current recommendation:

- team grouping: accepted
- K/D/A on complete-confirmed replays: accepted
- keep current anti-ceremony posture:
  - kills use a tight post-game cutoff
  - deaths keep a short tail
- do not change default buffers yet

Rationale:

- team grouping is already strong from direct offsets
- strict `death_buffer=0` makes fixture agreement worse
- raw late events exist, but not all short-tail late deaths are ceremony noise

## Follow-up

- if more truth becomes available, rerun this audit before changing K/D/A default buffers
- if a cleaner exact end-of-match signal is found, re-evaluate `kill_buffer` and `death_buffer` together
