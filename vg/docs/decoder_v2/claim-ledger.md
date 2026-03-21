# Claim Ledger

## Confirmed

| claim | status | basis |
|---|---|---|
| player block `+0xA5` is player entity id | `CONFIRMED` | raw fixture scan |
| player block `+0xA9` is hero id | `CONFIRMED` | raw fixture scan + truth match |
| player block `+0xD5` groups binary teams | `CONFIRMED` | raw fixture scan |
| hero decoding from player block is production-ready | `CONFIRMED` | 109/109 truth validation |

## Strong

| claim | status | basis |
|---|---|---|
| complete fixture winner decoding is usable | `STRONG` | 10/10 complete fixtures |
| complete fixture kills decoding is usable | `STRONG` | 98/99 complete fixtures |
| complete fixture deaths decoding is usable | `STRONG` | 97/99 complete fixtures |
| complete fixture assists decoding is usable | `STRONG` | 97/99 complete fixtures |
| kill/death/credit headers are semantically identified | `STRONG` | code + fixture behavior |

## Partial

| claim | status | counterexample |
|---|---|---|
| duration_seconds is a usable exact match end time | `PARTIAL` | exact 0/11, MAE 17.4s on complete fixtures |
| minion kill decoding is production-ready | `PARTIAL` | match 6, incomplete match 9 |
| complete replay detection rule is final | `PARTIAL` | current fixture set에서는 분리되지만 broader replay coverage는 부족 |
| match 6 minion residual has stable same-frame context candidate signals | `PARTIAL` | `28 04 3F`, `08 04 2C`, `18 04 1C`, `0x02`/`0x08` families are enriched, but cross-fixture proof is missing |

## Open

| claim | status | note |
|---|---|---|
| exact end-of-match signal | `UNKNOWN` | current crystal/last-death heuristic insufficient |
| canonical minion kill signal for all matches | `UNKNOWN` | `0x0E` alone appears incomplete |
| truth generation without result images | `UNKNOWN` | manifest alone is insufficient |
