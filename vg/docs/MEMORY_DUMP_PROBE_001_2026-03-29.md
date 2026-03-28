# Memory Dump Probe 001 2026-03-29

## Status

First dump generation was successful.

## Session

- manifest:
  - [manifest.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_001/manifest.json)
- home dump:
  - [menu_home.dmp](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_001/dumps/menu_home.dmp)
- home string probe:
  - [menu_home_string_probe.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_001/menu_home_string_probe.json)

## What Was Verified

- `Vainglory.exe` process could be dumped from a normal local session
- current `lean` dump mode worked
- produced dump size was about `20.3 MB`
- simple string extraction from the dump worked

## Immediate Findings

Strings present in the home dump include:

- `Vainglory`
- `Vainglory.exe`
- `D:\SteamLibrary\steamapps\common\Vainglory\Vainglory.exe`
- `Practice`
- `replay`
- `score`
- `surrender`

Interpretation:

- the dump is not empty or overly stripped
- the current dump mode is already good enough to continue with replay-state comparison work

## Phase Coverage So Far

Currently captured:

- `menu_home`
- `scoreboard_open`
- `scoreboard_closed`

Artifacts:

- [scoreboard_open.dmp](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_001/dumps/scoreboard_open.dmp)
- [scoreboard_closed.dmp](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_001/dumps/scoreboard_closed.dmp)
- [diff_menu_vs_scoreboard_open.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_001/diff_menu_vs_scoreboard_open.json)
- [diff_scoreboard_open_vs_closed.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_001/diff_scoreboard_open_vs_closed.json)

## Diff Notes

`menu_home -> scoreboard_open`

- added strings: `372`
- removed strings: `177`
- one directly useful added string already appeared:
  - `*GameMode_5v5_Practice*`

Interpretation:

- the scoreboard/open-match dump is materially different from the home dump
- state-dependent strings are entering memory
- simple string diff is noisy, but already confirms that phase transitions are visible in dumps

`scoreboard_open -> scoreboard_closed`

- added strings: `276`
- removed strings: `200`

Interpretation:

- opening and closing the scoreboard also changes in-memory string state
- this supports the current plan to compare scoreboard-open vs scoreboard-closed before chasing result-screen state

## Keyword Timeline Findings

Timeline artifact:

- [keyword_timeline.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/memory_sessions/replay_state_probe_001/keyword_timeline.json)

Most important result:

- `Temporary ashasha`
  - `menu_home`: `0`
  - `scoreboard_open`: present
  - `scoreboard_closed`: present
- `GameMode_5v5_Practice`
  - `menu_home`: `0`
  - `scoreboard_open`: present
  - `scoreboard_closed`: present

Interpretation:

- these are useful dynamic state markers
- they are absent in the home dump and appear once the live practice match state is active
- this is exactly the kind of phase-sensitive signal needed for replay-state reverse engineering

Less useful result:

- `HUDOpenScoreboardInputCommand`
- `HUDCloseScoreboardInputCommand`
- `ActionSetSurrenderStateRequest`
- `KindredHUDSurrender`

These appear in all captured phases so far.

Interpretation:

- they are probably static symbol / class-name strings from loaded code
- they are not good dynamic state discriminators by themselves

## Practical Takeaway

For the next dump session, prioritize:

- player names
- replay or game mode identifiers
- final result labels

Do not prioritize generic class/symbol names as primary phase markers.

## Limitation

String diff alone is still noisy.

That means the next useful layer is not "more random strings", but:

- replay-loaded dump
- targeted searches for player names / replay ids / HUD strings
- possibly narrower binary diffing around matched regions

## Next Target States

The next useful dumps are:

1. `replay_loaded_initial`
2. `scoreboard_open`
3. `scoreboard_closed`
4. `result_screen`

Those four, compared against `menu_home`, should be enough to start isolating:

- replay-specific strings
- scoreboard-specific strings
- result-specific strings
- possible KDA/minion/winner storage
