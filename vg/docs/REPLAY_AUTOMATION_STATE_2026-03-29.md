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
- target replay load has now been visually confirmed multiple times after overwrite
- build selection can be skipped with `Esc`
- replay HUD with exact player panels has now also been re-entered live

## Current Interpretation

The automation bottleneck is no longer basic navigation.

The remaining replay problem is:

- proving that the live temp slot was overwritten with the intended replay
- then proving that `다시보기` lands in that replay consistently

That is separate from the memory-dump track, which is already producing useful artifacts.

## Latest Live Result

Latest confirmed path:

- home
- play
- practice
- hero select
- talent select
- build skip via `Esc`
- in-match scoreboard
- surrender overlay
- `vgrplay` overwrite
- replay entry
- replay HUD visible
- full memory dumps captured from replay HUD states

Important consequence:

- replay automation is now strong enough to reach memory-useful replay HUD states repeatedly
- exact `8815_*` player labels were recovered from the later replay HUD full dumps
- the next live blocker is no longer replay entry itself
- result-screen capture has now also succeeded
- the next live blocker is no longer capture, but stable extraction from result-screen memory

## Memory Track Caveat

Do not treat raw full-dump keyword hits like `DIOR`, `korea`, or `rui` as proof of exact target player identity yet.

Current audit shows:

- `DIOR` hits are asset/table noise
- `korea` hits are mostly locale-table noise
- `rui` hits are too noisy to trust

The strongest replay-load proof remains:

- successful `vgrplay` overwrite
- visual confirmation of the target replay HUD
