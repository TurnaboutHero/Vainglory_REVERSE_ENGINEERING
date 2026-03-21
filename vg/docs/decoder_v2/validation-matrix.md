# Validation Matrix

Source:
- `vg/output/decode_tournament_validation_v2.json`
- `vg/output/decoder_v2_foundation_report.json`
- `vg/output/truth_inventory.json`
- `vg/output/decoder_v2_residual_signal_research.json`
- `vg/output/decoder_v2_minion_window_match6.json`

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

## Completeness Gate

현재 fixture 분류:
- `complete_confirmed`: 10
- `incomplete_confirmed`: 1
- `completeness_unknown`: 0

의미:
- 현재 tournament fixture 집합에선 conservative gate가 전부 분류에 성공한다.
- 다만 broader replay coverage가 낮아서 아직 final rule로 선언하긴 이르다.
