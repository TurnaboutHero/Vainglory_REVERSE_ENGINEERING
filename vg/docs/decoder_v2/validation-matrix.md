# Validation Matrix

Source:
- `vg/output/decode_tournament_validation_v2.json`
- `vg/output/decoder_v2_foundation_report.json`
- `vg/output/truth_inventory.json`
- `vg/output/decoder_v2_residual_signal_research.json`
- `vg/output/decoder_v2_minion_window_match6.json`
- `vg/output/decoder_v2_minion_window_complete.json`
- `vg/output/truth_source_priority.json`
- `vg/output/decoder_v2_completeness_audit.json`

## All Fixtures

| field | correct / total | pct |
|---|---:|---:|
| hero | 109 / 109 | 100.0% |
| team | 109 / 109 | 100.0% |
| winner | 10 / 11 | 90.9% |
| kills | 104 / 109 | 95.4% |
| deaths | 102 / 109 | 93.6% |
| assists | 102 / 109 | 93.6% |
| minion_kills | 69 / 89 | 77.5% |

## Complete Fixtures Only

| field | correct / total | pct |
|---|---:|---:|
| winner | 10 / 10 | 100.0% |
| kills | 98 / 99 | 99.0% |
| deaths | 97 / 99 | 98.0% |
| assists | 97 / 99 | 98.0% |
| minion_kills | 69 / 79 | 87.3% |

## Duration

| metric | value |
|---|---:|
| exact matches | 0 / 11 |
| MAE all fixtures | 128.2s |
| MAE complete fixtures | 17.4s |
| max abs error complete fixtures | 65s |

## Known Outliers

| match | issue |
|---|---|
| match 6 | complete fixture인데 K/D/A와 minion에 오차 집중 |
| match 9 | incomplete fixture, winner/KDA/minion/duration 전부 붕괴 |

## Truth Coverage

| metric | value |
|---|---:|
| local replay directories | 56 |
| truth-covered directories | 11 |
| missing directories | 45 |
| coverage | 19.6% |
| directories with result image | 11 |

해석:
- 현재 truth는 tournament set에 집중되어 있다.
- replay 풀 전체 대비 검증 커버리지는 아직 낮다.

## Truth Audit

Source:
- `vg/output/truth_audit.json`
- `.omx/tournament_truth_ocr_latest.json`

| metric | value |
|---|---:|
| audited matches | 11 |
| score mismatch matches | 8 |
| duration mismatch matches | 0 |
| player rows compared | 110 |
| minion mismatches | 47 |
| kill mismatches | 4 |
| death mismatches | 4 |
| assist mismatches | 4 |

해석:
- OCR는 duration/K/D/A 일부에는 쓸 수 있지만
- score와 minion은 현재 품질이 낮아 truth source로 바로 믿기 어렵다

## Residual Signal Audit

Source:
- `vg/output/decoder_v2_residual_signal_research.json`

| metric | value |
|---|---:|
| complete-fixture player rows | 78 |
| positive residual rows (`truth - 0x0E > 0`) | 7 |
| best credit candidate F1 | 0.50 |
| best credit candidate exact-match rate | 0.14 |

해석:
- 기존 `action 0x04` residual 후보들은 `MAE`만 보면 좋아 보일 수 있다.
- 하지만 sparse residual 기준 precision/recall/exact-match로 다시 보면 아직 general rule이 아니다.
- 즉 `0x04`는 direct minion signal이 아니라 보조 context signal 후보로 남겨두는 편이 더 안전하다.

## Match 6 Window Audit

Source:
- `vg/output/decoder_v2_minion_window_match6.json`

핵심 차이:
- residual-positive player 쪽에서 `28 04 3F` header가 `~2.75x` 더 자주 보인다.
- residual-positive player 쪽에서 `08 04 2C` header가 `~2.00x` 더 자주 보인다.
- residual-positive player 쪽에서 `18 04 1C` header도 `~1.93x` 더 자주 보인다.
- same-frame credit pattern은 `0x02` family와 일부 `0x08`/`0x00` bucket이 positive 쪽에 치우친다.
- nonpositive 쪽은 `0x03` family가 압도적이다.

해석:
- match 6 undercount는 완전한 random noise보다, 특정 same-frame context family를 놓치는 쪽에 더 가깝다.
- 다만 이 결과는 아직 match 6 중심 evidence라서, complete fixture 전체로 일반화 검증이 필요하다.

## Complete-Fixture Window Audit

Source:
- `vg/output/decoder_v2_minion_window_complete.json`

핵심 차이:
- complete fixture 전체로 집계해도 positive residual rows는 사실상 한 경기(match 6)에서만 나온다.
- 그래도 `28 04 3F`, `08 04 2C`, `18 04 1C`는 global aggregate에서도 positive 쪽이 더 높다.
- same-frame `0x02` family와 일부 `0x00`/`0x08` bucket도 positive 쪽에 더 붙는다.

해석:
- 이 결과는 “새 전역 minion rule이 보였다”보다 “match 6이 정말 특이 케이스다”에 가깝다.
- 다음 단계는 global rule 추가보다 match 6 replay-family 차이를 설명하는 것이다.

## Finals Series Effect

Source:
- `vg/output/decoder_v2_minion_series_profile.json`
- `vg/output/decoder_v2_minion_series_peer_match6.json`
- `vg/output/decoder_v2_minion_pattern_family_match6.json`
- `vg/output/decoder_v2_action02_value_compare_match6.json`

핵심 차이:
- Finals 1-4는 모두 `GameMode_5v5_Ranked`, `Sovereign Rise`, `team_size = 5`라서 format 차이로 설명되지 않는다.
- Finals series 전체는 다른 tournament series보다 `0x02` solo-subfamily가 높다.
- 하지만 Finals 2는 same-series peer와 비교해도 특정 `0x02` bucket이 더 높다.

대표 예:
- `Kestrel 0x02@20.0`: target `117`, same-series mean `30`, cross-series mean `6`
- `Samuel 0x02@17.4`: target `667`, same-series mean `416`, cross-series mean `113`
- `Kinetic 0x02@9.54`: target `444`, same-series mean `350.5`, cross-series mean `59.5`
- `Grumpjaw 0x02@4.0`: target `222`, same-series mean `0`, cross-series mean `0`

해석:
- 현재 minion blocker는 “Finals series 효과 + Finals-2-specific amplification” 구조에 가깝다.
- 가장 강한 shared signature는 `0x02 family`다.

## Truth Source Priority

Source:
- `vg/output/truth_source_priority.json`

| metric | value |
|---|---:|
| immediately labelable | 0 |
| manifest-only | 41 |
| raw-only | 4 |

해석:
- immediate OCR backlog가 0이라서 OCR scale-out은 지금 우선순위가 낮다.
- truth 확장의 실제 병목은 manifest-only 41개에 대한 result image / score source 확보다.

## Completeness Gate

현재 fixture 분류:
- `complete_confirmed`: 10
- `incomplete_confirmed`: 1
- `completeness_unknown`: 0

의미:
- 현재 tournament fixture 집합에선 conservative gate가 전부 분류에 성공한다.
- 다만 broader replay coverage가 낮아서 아직 final rule로 선언하긴 이르다.

## Broader Completeness Audit

Source:
- `vg/output/decoder_v2_completeness_audit.json`

| metric | value |
|---|---:|
| total replays audited | 56 |
| complete_confirmed | 53 |
| completeness_unknown | 0 |
| incomplete_confirmed | 3 |
| review queue size | 27 |

해석:
- 현재 gate는 broader replay pool에서도 usable 수준으로 올라왔다.
- winner/K/D/A accepted replay도 53개까지 올라왔다.
- broader replay 풀은 이제 conservative policy 기준으로 complete/incomplete가 모두 분류된다.
