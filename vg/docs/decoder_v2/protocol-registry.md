# Protocol Registry

## Status Vocabulary

- `CONFIRMED`: fixture-backed direct claim
- `STRONG`: 근거는 강하지만 직접 offset claim은 아니거나 반례 탐색이 더 필요
- `PARTIAL`: 일부 조건에서만 맞음
- `DISPUTED`: 반례 존재
- `UNKNOWN`: 의미 미확정

## Player Block

| id | location | type | meaning | status | evidence |
|---|---|---|---|---|---|
| `player_block.entity_id` | `+0x0A5` | `u16 le` | player entity id | `CONFIRMED` | 11 fixture direct scan |
| `player_block.hero_id` | `+0x0A9` | `u16 le` | hero selection id | `CONFIRMED` | 107/107 normalized match |
| `player_block.hero_hash` | `+0x0AB` | `bytes[4]` | hero fingerprint bytes | `STRONG` | docs + code usage |
| `player_block.team_byte` | `+0x0D5` | `u8` | binary team grouping byte | `CONFIRMED` | 110 player blocks |

## Event Headers

| id | header | entity field | timestamp field | meaning | status |
|---|---|---|---|---|---|
| `event.kill` | `18 04 1C` | `+5 BE` | `-7 f32 BE` | kill event family | `CONFIRMED` |
| `event.death` | `08 04 31` | `+5 BE` | `+9 f32 BE` | death event family | `CONFIRMED` |
| `event.credit` | `10 04 1D` | `+5 BE` | `+7 f32 BE` | credit / gold / assist family | `STRONG` |
| `event.item_acquire` | `10 04 3D` | `+5 BE` | `+17 f32 BE` | item acquisition family | `STRONG` |

## Notes

- registry의 canonical source는 code다:
  - `vg/decoder_v2/registry.py`
- 이 문서는 사람용 요약본이다.
