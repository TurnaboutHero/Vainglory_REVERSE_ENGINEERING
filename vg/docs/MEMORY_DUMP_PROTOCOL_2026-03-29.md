# Memory Dump Protocol 2026-03-29

## Goal

Use replay-state memory dumps to answer questions that `.vgr` parsing alone still leaves ambiguous:

- exact in-engine K/D/A state timing
- minion/storage semantics
- winner and result-state storage
- replay timeline / scoreboard state transitions

## Current Tooling

- direct game executable:
  - [Vainglory.exe](/D:/SteamLibrary/steamapps/common/Vainglory/Vainglory.exe)
- replay injection tool:
  - `vgrplay.exe`
- Windows UI control:
  - `Windows-MCP`
- dump generation:
  - [windows_minidump.py](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/tools/windows_minidump.py)
- dump string diff:
  - [dump_string_diff.py](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/tools/dump_string_diff.py)
- session manifest builder:
  - [memory_session_manifest.py](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/tools/memory_session_manifest.py)

## Recommended Replay-State Phases

Start with replay mode, not live PvP.

Recommended phases:

1. `menu_home`
2. `replay_loaded_initial`
3. `scoreboard_open`
4. `scoreboard_closed`
5. `result_screen`

## Why Replay First

- replay is repeatable
- same state can be revisited
- anti-cheat risk is lower than live competitive play
- the current decoder bottleneck is understanding recorded state, not live networking

## Dump Strategy

Use `lean` first:

- smaller
- faster
- enough for string/state exploration

Escalate to `full` only if:

- strings are insufficient
- target structures are missing from lean dumps

## Session Workflow

1. build a session manifest
2. capture screenshot + dump for each phase
3. diff strings between adjacent dumps
4. search for:
   - player names
   - hero names
   - replay uuid
   - score values
   - kill/death/assist counters
   - minion or bounty counters

## Commands

Create a session manifest:

```powershell
python -m vg.tools.memory_session_manifest `
  --session-root vg/output/memory_sessions/session_001 `
  --replay-source-dir "D:\Desktop\My Folder\Game\VG\vg replay\21.11.17\리플" `
  --replay-name "0f66f336-3e1c-11eb-ad3d-02ea73c392db-28c9273d-f413-4d68-898c-5388383873f5"
```

Create a dump from a running process:

```powershell
python -m vg.tools.windows_minidump `
  --process-name Vainglory.exe `
  --mode lean `
  --output vg/output/memory_sessions/session_001/dumps/menu_home.dmp
```

Diff dump strings:

```powershell
python -m vg.tools.dump_string_diff `
  --before vg/output/memory_sessions/session_001/dumps/menu_home.dmp `
  --after vg/output/memory_sessions/session_001/dumps/replay_loaded_initial.dmp `
  -o vg/output/memory_sessions/session_001/diff_menu_vs_loaded.json
```

## Interpretation Rules

- if a value only appears when scoreboard is open, it may be a UI model
- if it exists before scoreboard open, it is likely engine state
- if a value changes only at result screen, it may be final scoreboard state
- if it persists after scoreboard close, it is likely cached or engine-owned

## Cautions

- dump files can be large
- do not modify process memory
- stay on offline practice / replay paths
- use lean dumps first
