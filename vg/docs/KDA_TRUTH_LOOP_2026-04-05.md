# KDA Truth Loop 2026-04-05

## Why this branch exists

KDA is the highest-ROI accuracy lane.
The current path to 100% is not broad `.vgr` heuristic expansion first.
It is:

- identify truth residual replays
- capture result-screen truth for those replays
- run correction/autobundle
- validate corrected rows against truth
- rebuild corrected export

Minion work stays deferred until this loop is exhausted.

## Current blockers

- priority-1 tournament replays still have truth residuals and no result-screen dump
- at least one existing captured session has no manifest replay name, which blocks readiness classification
- some decoded replays have no result-screen dump yet

## Active loop

1. Refresh `readiness`, `validation`, and `backlog`.
2. Select the top backlog replay.
3. Create or repair a capture session manifest.
4. Capture result-screen dump and screenshot.
5. Run autobundle and correction inventory.
6. Re-run validation.
7. Rebuild corrected export.

## Success condition

- every truth-covered replay is either parser-correct or corrected-export-correct
- remaining open items are only uncaptured replays
- no known captured KDA dump is blocked by missing metadata
