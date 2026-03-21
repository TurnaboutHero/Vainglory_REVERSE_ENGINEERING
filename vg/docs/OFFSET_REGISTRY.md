# Offset Registry

현재 `decoder_v2` 기초 작업에서 관리하는 핵심 claim은 다음과 같다.

## Player Block

| Claim ID | Offset | Meaning | Status |
|---|---:|---|---|
| `player_block.entity_id` | `0x0A5` | player entity id | confirmed |
| `player_block.hero_id` | `0x0A9` | hero selection id | confirmed |
| `player_block.hero_hash` | `0x0AB` | hero fingerprint bytes | supported |
| `player_block.team_byte` | `0x0D5` | binary team grouping byte | confirmed |

## Event Headers

| Claim ID | Header | Meaning | Status |
|---|---|---|---|
| `event.kill` | `18 04 1C` | kill event family | confirmed |
| `event.death` | `08 04 31` | death event family | confirmed |
| `event.credit` | `10 04 1D` | credit / gold / assist event family | supported |
| `event.item_acquire` | `10 04 3D` | item acquire event family | supported |

## Decoder Field Status

| Field | Status | Notes |
|---|---|---|
| hero | confirmed | direct offset |
| team_grouping | confirmed | direct offset |
| winner_complete_fixture | supported | complete replay 기준 강함 |
| kills | supported | complete replay 기준 강함 |
| deaths | supported | complete replay 기준 강함 |
| assists | supported | complete replay 기준 강함 |
| minion_kills | open | outlier 존재 |
| duration_seconds | approximate | exact field 아님 |

세부 evidence는 `vg/decoder_v2/registry.py`와 `vg/decoder_v2/validation.py`를 기준으로 갱신한다.
