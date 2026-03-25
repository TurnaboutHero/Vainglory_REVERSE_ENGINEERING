# Truth Capture Pack 2026-03-26

Source:
- [truth_capture_pack_top20.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/truth_capture_pack_top20.json)
- [truth_labeling_queue.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/truth_labeling_queue.json)

## Purpose

The labeling queue ranks what to do next.

The capture pack turns the top part of that queue into an immediately usable bundle:

- replay path
- manifest link
- accepted safe fields
- prefilled stub
- capture goal
- capture requirements

## Current Pack

Current pack size:

- `20` items

All current top items are dominated by the same validation track:

- `validate_5v5_ranked_minion_and_kda_policy`

That is the correct current focus.

## Why These 20 Matter

For these items:

- replay completeness is already good enough
- hero/team/entity are already trusted
- winner/KDA are already accepted
- truth is the missing piece

That means each newly labeled replay does more than increase coverage.

It directly strengthens:

- minion-policy validation
- broader KDA/winner generalization confidence
- non-tournament replay coverage

## What To Capture

Each pack item explicitly asks for:

- final winner
- final team score
- per-player K/D/A
- per-player gold or bounty if visible
- per-player minion kills or bounty if visible

This keeps capture work aligned with the current decoder bottlenecks.

## Operational Use

If work is manual:

- start at item `1`
- label in order
- feed finished results back into truth JSON or an intermediate reviewed source

If work is automated later:

- use this pack as the first automation batch
- do not start from the raw `truth_stubs.json`
- start from the capture pack instead

## Current Recommendation

Use:

- [truth_labeling_queue.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/truth_labeling_queue.json) for global prioritization
- [truth_capture_pack_top20.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/truth_capture_pack_top20.json) for immediate execution
