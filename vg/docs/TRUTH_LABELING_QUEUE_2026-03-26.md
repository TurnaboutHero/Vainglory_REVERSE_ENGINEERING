# Truth Labeling Queue 2026-03-26

Source:
- [truth_labeling_queue.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/truth_labeling_queue.json)

## Purpose

The decoder is no longer the only bottleneck.

Truth coverage is.

This queue ranks the `45` uncovered replay directories by expected labeling value so manual review or later GUI automation can start with the highest-yield targets.

## Ranking Logic

Highest score goes to stubs with:

- `complete_confirmed`
- `5v5`
- `GameMode_5v5_Ranked`
- `winner` accepted
- `kills/deaths/assists` accepted
- manifest linked

This is deliberate.

If we have to spend human or automation effort, the first target should be replays where:

- decoder_v2 already trusts hero/team/entity/winner/KDA
- only truth labels are missing
- minion is still withheld

## Current Top Tier

The current top queue is dominated by:

- complete-confirmed
- 5v5 ranked
- manifest-linked
- winner/KDA accepted

Examples near the top:

- `21.11.17\\리플`
- `21.11.22\\1`
- `21.11.22\\2`
- `22.06.06\\EA vs SEA\\cache 1\\cache`
- `23.02.07\\cache\\cache`

These are the best first candidates for truth capture.

## Why This Matters

These top rows are exactly the replays that can most quickly answer:

- does `nonfinals-baseline-0e` keep holding on broader non-tournament truth?
- does the current KDA/winner policy generalize outside the tournament set?
- how far can truth expansion move minion validation without any new decoding rule?

## Practical Recommendation

If manual labeling starts tomorrow, start from the top of this queue.

If GUI automation becomes available later, automate this queue in order.

Do not start from:

- incomplete-confirmed practice/debug replays
- completeness-unknown low-value stubs
- raw-only directories without manifests

Those are lower-value truth targets.
