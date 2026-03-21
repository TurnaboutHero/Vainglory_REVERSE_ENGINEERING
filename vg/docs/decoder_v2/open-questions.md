# Open Questions

## 1. Exact match-end signal은 무엇인가?

현재 후보:
- crystal death timestamp
- last player death timestamp
- late item timestamp

필요한 실험:
- complete fixture 전체에서 후보별 MAE 비교
- incomplete fixture에서 false positive / false negative 패턴 분리

성공 기준:
- complete fixture에서 더 낮은 MAE
- incomplete fixture에서는 잘못된 duration을 내기보다 reject 가능

## 2. Minion kill의 canonical signal은 무엇인가?

현재 후보:
- `10 04 1D` with `value == 1.0` and action `0x0E`

문제:
- complete fixture match 6에서 광범위한 undercount
- `0x0F`는 count가 같게 반복되므로 단순 합산 해법은 아님

현재까지 확인된 것:
- simple feature 비교에서 `0x0E@1.0`와 `0x0F@1.0`가 complete fixture 기준 MAE가 가장 낮다
- `0x0D_total`, `0x0E+0D`, `0x0E+0F` 같은 단순 조합은 오히려 더 나쁘다
- 즉 missing family가 있더라도 단순 additive credit 합산은 해법이 아니다
- generic player-action count도 `0x0E/0x0F`보다 훨씬 약하다
- match 6 tail activity에는 `0x05`, `0x00`, `0x07`, `0x01`, `0x44` 계열이 남지만, 현재로선 missing CS를 설명하는 일반 규칙은 보이지 않는다
- positive residual은 complete fixture 78 player row 중 7개뿐이다
- `action 0x04` credit family는 residual 후보처럼 보였지만, 현재는 `MAE` 편향 가능성이 더 크다
  - value bucket count를 residual에 바로 맞춰 보면 `MAE ~= 0.9~1.2`가 나오는 bucket이 많다
  - 하지만 sparse residual 전용 report 기준으로는 precision/recall이 낮고, exact-match도 일부 player에서만 우연히 맞는다
  - 즉 `0x04`는 direct minion signal로 승격할 근거가 없고, 현재는 보조 context signal 후보로 남겨두는 편이 맞다
- residual-signal report의 현재 결론:
  - top credit 후보도 `f1_positive ~= 0.5` 수준이다
  - top player-action 후보는 residual-positive 7개 행을 모두 커버하는 경우가 있지만 false positive가 많고 count scale도 residual과 맞지 않는다
  - 따라서 아직 production rule이 될 수 있는 canonical residual feature는 없다
- same-frame window report의 현재 결론:
  - match 6 residual-positive player 쪽에서 `28 04 3F`, `08 04 2C`, `18 04 1C` header가 더 자주 보인다
  - same-frame credit pattern은 `0x02` 계열과 `0x08@3.6`, `0x08@4.8`, 일부 `0x00` value bucket이 positive 쪽에 치우친다
  - 반대로 nonpositive 쪽은 `0x03` family가 훨씬 강하다
  - 다만 이 차이는 아직 match 6 기반이므로 cross-fixture generalization이 필요하다

필요한 실험:
- 같은 시간대의 다른 credit variants 조사
- kill/assist/credit와의 상관관계 조사
- player별 undercount pattern 비교
- cumulative curve 비교
- `MAE` 대신 sparse residual 전용 precision/recall/exact-match 기준으로 후보를 재평가
- same-frame window report를 complete fixture 전체로 확장해서 header/pattern enrichment가 유지되는지 확인

## 3. Incomplete replay를 어떻게 자동 감지할 것인가?

현재 관찰:
- crystal death 부재
- duration 급락
- KDA/minion 동시 붕괴
- frame 수 부족
- `max_death_header_ts - max_player_death_ts` 큰 차이

필요한 실험:
- incomplete fixture 반례 수집
- complete fixture와 분리 가능한 gate 정교화

## 4. Winner를 어떤 조건에서만 허용할 것인가?

현재:
- complete fixture에서는 strong
- incomplete fixture에서는 오염 가능

필요한 실험:
- crystal evidence 기반 winner
- kill asymmetry fallback 사용 조건 제한

## 5. Truth coverage를 어떻게 늘릴 것인가?

현재 관찰:
- 로컬 replay 디렉터리 56개 중 truth 연결은 11개
- missing은 45개
- result image가 붙은 디렉터리는 11개뿐이고, 현재는 모두 truth-covered
- missing 45개 중 41개는 manifest는 있지만 result image가 없음

의미:
- 당장 OCR만으로 truth를 늘릴 수 있는 backlog는 거의 없다
- 추가 truth 생성은 result image 재수집 또는 다른 truth source 확보가 필요하다
- OCR 재활용이 가능하더라도 score/minion은 별도 검증이 필요하다

## 6. replayManifest는 truth source가 될 수 있는가?

현재 관찰:
- `replayManifest-*.txt`는 대부분 `match_uuid-session_uuid` 한 줄만 제공한다
- player / score / winner / duration / mode는 담고 있지 않다

판단:
- manifest는 replay linking에는 유용하다
- 하지만 전적검색용 truth를 직접 생성하는 source로는 부족하다

## 7. OCR truth를 어디까지 신뢰할 수 있는가?

현재 관찰:
- audited matches: 11
- score mismatch matches: 8
- duration mismatch matches: 0
- player-level mismatch:
  - minion: 47/110
  - kills: 4/110
  - deaths: 4/110
  - assists: 4/110

의미:
- OCR는 duration/K/D/A 보조 소스로는 쓸 수 있다
- 하지만 score/minion은 현재 상태로는 ground truth로 바로 승격하면 안 된다
