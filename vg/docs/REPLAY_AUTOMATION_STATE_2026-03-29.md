# Replay Automation State 2026-03-29

## Current Status

The replay automation path is partially working.

Confirmed:

- home -> play
- practice mode
- hero selection
- talent selection
- build selection
- in-match HUD
- scoreboard open
- surrender approval
- replay reconnect / loading screen
- replay-mode HUD state once
- build selection can be skipped with `Esc`
- the same left-side button coordinate used for surrender can also trigger replay entry after overwrite when timing lines up

Not yet reliable:

- target replay overwrite confirmation every run
- stable `replay_loaded_initial` for the intended target replay
- stable result-screen arrival
- reliable replay-menu navigation after target replay has loaded

## New Tooling

- [vgrplay_inject.py](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/tools/vgrplay_inject.py)

Purpose:

- detect the current temp replay slot
- run `vgrplay.exe`
- report changed temp `.vgr` files
- make overwrite success/failure easier to inspect

## Latest Interpretation

Current strongest reading:

- `vgrplay` overwrite itself is succeeding
- the remaining instability is mostly post-overwrite UI timing
- `Esc` is now the preferred build-selection path because it removes one unreliable click stage

## Current Interpretation

The automation bottleneck is no longer basic navigation.

The remaining replay problem is:

- proving that the live temp slot was overwritten with the intended replay
- then proving that `다시보기` lands in that replay consistently

That is separate from the memory-dump track, which is already producing useful artifacts.
