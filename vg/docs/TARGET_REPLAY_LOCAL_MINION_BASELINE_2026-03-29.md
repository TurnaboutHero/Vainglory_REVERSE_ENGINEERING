# Target Replay Local Minion Baseline 2026-03-29

## Artifact

- [local_minion_baseline_audit_target.json](/D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/local_minion_baseline_audit_target.json)

## Local Pool

Replay root:

- [vg replay](/D:/Desktop/My%20Folder/Game/VG/vg%20replay)

Current audit base:

- complete replays: `53`
- non-Finals complete replays: `49`

## Target Replay Percentiles

Target replay:

- `0f66f336-3e1c-11eb-ad3d-02ea73c392db-28c9273d-f413-4d68-898c-5388383873f5`

Per-hero baseline `0x0E` percentiles in the local non-Finals complete pool:

- `8815_DIOR` — Baron — `145`
  - hero pool count: `21`
  - percentile: `0.4286`
- `8815_Bro` — Tony — `26`
  - hero pool count: `11`
  - percentile: `0.8182`
- `8815_mumu` — Phinn — `11`
  - hero pool count: `18`
  - percentile: `0.5556`
- `8815_nok` — Leo — `100`
  - hero pool count: `4`
  - percentile: `0.25`
- `8815_Sui` — Magnus — `138`
  - hero pool count: `14`
  - percentile: `0.3571`
- `8815_korea` — Vox — `119`
  - hero pool count: `10`
  - percentile: `0.3`
- `8815_LeeJiEun` — Ringo — `124`
  - hero pool count: `7`
  - percentile: `0.4286`
- `8815_zm` — Fortress — `19`
  - hero pool count: `4`
  - percentile: `0.5`
- `8815_rui` — Grace — `58`
  - hero pool count: `14`
  - percentile: `0.5`
- `8815_lamy_KR` — Ardan — `6`
  - hero pool count: `25`
  - percentile: `0.52`

## Interpretation

This replay does not look like a broad minion-baseline outlier within the local non-Finals complete pool.

Most players sit around the middle of their hero-specific local distribution.

That makes this replay a good operational example of:

- exact `.vgr` identity recovery
- accepted winner/KDA export
- optional non-Finals minion export

not an example of the Finals/outlier minion problem.

## Consequence

The current minion blocker remains concentrated in:

- Finals-series behavior
- outlier replay families

not in ordinary non-Finals complete replays like this one.
