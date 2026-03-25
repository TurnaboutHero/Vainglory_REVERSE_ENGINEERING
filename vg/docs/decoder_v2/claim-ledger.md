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
| binary team grouping is stable for index export | `STRONG` | 110 player blocks, team bytes `{1:55, 2:55}` on truth fixtures |
| current post-game K/D buffers are conservative enough to exclude known late kills without dropping short-tail real deaths | `STRONG` | fixture audit shows `death_buffer=0` is worse than `death_buffer=10` |

## Partial

| claim | status | counterexample |
|---|---|---|
| duration_seconds is a usable exact match end time | `PARTIAL` | exact 0/11, MAE 17.4s on complete fixtures |
| minion kill decoding is production-ready | `PARTIAL` | match 6, incomplete match 9 |
| complete replay detection rule is final | `PARTIAL` | current local replay pool is fully partitioned (`53 complete / 3 incomplete`), but external replay-family validation is still missing |
| match 6 minion residual has stable same-frame context candidate signals | `PARTIAL` | `28 04 3F`, `08 04 2C`, `18 04 1C`, and especially `0x02` family are enriched, but production-ready correction evidence is still missing |

## Open

| claim | status | note |
|---|---|---|
| exact end-of-match signal | `UNKNOWN` | current crystal/last-death heuristic insufficient |
| canonical minion kill signal for all matches | `UNKNOWN` | `0x0E` alone appears incomplete |
| truth generation without result images | `UNKNOWN` | manifest alone is insufficient |
