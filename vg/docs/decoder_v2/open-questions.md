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
  - complete fixture 전체로 집계해도 positive residual은 사실상 한 경기(match 6)에만 몰려 있다
  - 즉 다음 질문은 “전역 규칙이 무엇인가”보다 “왜 match 6만 다른가”에 더 가깝다
- same-hero compare의 현재 결론:
  - match 6 positive residual players의 same-hero peer는 대부분 다른 complete 경기에서 residual `0`이다
  - 일부 pattern은 same hero에서도 보이지만, match 6에서만 count scale이 유난히 커진다
  - 즉 현재 outlier는 hero 자체보다 replay-family/context 차이에 더 가깝다
  - 예:
    - Kestrel은 `0x02@20.0`가 peer mean `14.0` 대비 target `117`
    - Samuel은 `0x02@17.4`가 peer mean `340.25` 대비 target `667`
    - Grumpjaw는 `0x02@4.0`가 peer peer baseline `0`인데 target `222`
- action-family compare의 현재 결론:
  - match 6 positive residual players 다수에서 `0x02 family` total 자체가 same-hero peer 평균보다 크게 높다
  - 예:
    - Kestrel `0x02` total: target `141`, peer mean `78.0`
    - Samuel `0x02` total: target `804`, peer mean `395.25`
    - Grumpjaw `0x02` total: target `240`, peer mean `25.75`
    - Kinetic `0x02` total: target `145`, peer mean `68.75`
  - 즉 현재 minion outlier의 가장 강한 replay-family signature는 `0x02` family다
- provenance/context profile의 현재 결론:
  - 핵심 `0x02` outlier value들은 same-frame에서 거의 항상 `0x06@3.0`, `0x08@0.6`, `0x03@1.0`과 같이 뜬다
  - `0x02@17.4`, `0x02@14.34`, `0x02@9.54`, `0x02@4.0`는 shared cluster가 거의 없고 사실상 solo event에 가깝다
  - `0x02@20.0`와 `0x02@-50.0`만 일부 multi-player cluster가 있지만 shared rate 자체는 낮다
  - 즉 match 6 minion blocker는 “0x02 = 일반 팀 XP 공유” 한 줄로는 설명되지 않고, `0x02` 내부 subfamily를 분리해야 한다
  - 현재 가장 안전한 taxonomy 초안은:
    - `shared XP / shared reward candidate`
    - `solo-cluster / replay-family outlier candidate`
  - 현재 더 구체적인 working taxonomy는:
    - `solo_subfamily_candidate`
      - `0x02@17.4`
      - `0x02@14.34`
      - `0x02@9.54`
      - `0x02@4.0`
  - `mixed_or_shared_subfamily_candidate`
    - `0x02@20.0`
    - `0x02@-50.0`
  - outlier risk report의 현재 결론:
    - `solo_subfamily` excess만으로는 positive residual을 clean하게 분리하지 못한다
    - Finals 1/3/4 같은 zero-residual rows도 높은 solo excess를 가진다
    - 즉 `solo_subfamily_total`을 전역 minion 보정식으로 쓰면 false positive가 크다
- series compare의 현재 결론:
  - Finals series 전체가 다른 series보다 `0x02` solo-subfamily가 높다
  - 하지만 Finals 2는 same-series peer와 비교해도 특정 bucket이 더 높다
  - 즉 현재 문제는 “Finals 전체 replay-family 효과”와 “Finals 2 특이치”가 겹친 구조다
  - mode/map/team_size는 Finals 1-4가 전부 같아서 이 차이를 설명하지 못한다
  - hero affinity의 현재 결론:
    - `0x02@17.4`는 사실상 `Samuel` 전용
    - `0x02@14.34`는 `Celeste` 중심, 일부 `Magnus`
    - `0x02@9.54`는 `Kinetic` 중심, 일부 `Ishtar`
    - `0x02@4.0`는 `Caine` 중심이지만 `Grumpjaw`/`Kestrel`도 포함
    - `0x02@20.0`, `0x02@-50.0`는 여러 hero에 넓게 퍼진다
  - practical takeaway:
    - `0x02`는 현재 production decoder rule이 아니라 replay-family risk signal로만 써야 한다
    - 지금 단계에서 가장 위험한 overfit은 `solo_subfamily_total` 또는 특정 `0x02` bucket count를 minion 보정식으로 직접 넣는 것이다
  - dangerous overfit은 `0x02 family` 또는 특정 `0x02` bucket count를 바로 `0x0E` baseline에 더하는 규칙이다
  - no-go rules:
    - `0x02 family` count를 전역 minion 보정식으로 직접 쓰지 않는다
    - Finals-2 bucket pattern을 다른 replay family에 일반화하지 않는다
    - hero-only correction rule로 단순화하지 않는다
    - OCR minion/score를 ground truth로 승격하지 않는다
  - ratio research의 현재 결론:
    - raw count보다 `0x02@20.0_ratio`가 조금 낫지만, best rule도 `precision 0.75 / recall 0.43` 수준이다
    - `solo_ratio`도 `precision 0.60 / recall 0.43` 수준이라 production rule로는 아직 부족하다
    - 즉 ratio normalization만으로도 minion export를 안전하게 열기엔 근거가 약하다
  - acceptance gate research의 현재 결론:
    - current truth 기준 `Finals 제외` gate는 baseline `0x0E` minion을 `precision 1.0`으로 받는다
    - coverage는 `0.5128`라 낮지만, 지금까지 나온 첫 보수적 partial acceptance 후보다
    - hybrid candidate `nonfinals_or_mixed_ratio<=0.1351`는 `precision ~= 0.9796`, `coverage ~= 0.6282`
    - 즉 partial acceptance는 가능성이 있지만, 아직 truth coverage가 낮아서 default policy 승격은 이르다
    - 다만 truth coverage가 낮아서 이걸 default policy로 바로 승격하면 위험하다
    - 구현 관점에선 현재 `index_export`에 optional policy로만 노출하는 것이 맞다
    - current optional policy names:
      - `nonfinals-baseline-0e`
      - `nonfinals-or-low-mixed-ratio-experimental`
    - current policy validation summary:
      - `none` -> `accepted_rows 0`, `coverage 0.0`
      - `nonfinals-baseline-0e` -> `accepted_rows 40`, `precision 1.0`, `coverage 0.5128`
      - `nonfinals-or-low-mixed-ratio-experimental` -> `accepted_rows 49`, `precision 0.9796`, `coverage 0.6282`
  - prior-research tension:
    - 기존 repo의 주류 해석은 `0x02 = XP / team-wide sharing`
    - 하지만 현재 match 6 evidence는 `0x02` 내부에 solo-like subfamily와 mixed/shared-like subfamily가 같이 있음을 시사한다
    - 즉 과거 해석을 버리는 게 아니라, `0x02`를 단일 semantic으로 쓰는 단계가 끝났다고 보는 편이 맞다

필요한 실험:
- 같은 시간대의 다른 credit variants 조사
- kill/assist/credit와의 상관관계 조사
- player별 undercount pattern 비교
- cumulative curve 비교
- `MAE` 대신 sparse residual 전용 precision/recall/exact-match 기준으로 후보를 재평가
- same-frame window report를 match 6 특이점 분석 쪽으로 더 좁혀서, 어떤 replay-family 차이가 있는지 확인

## 3. Incomplete replay를 어떻게 자동 감지할 것인가?

현재 관찰:
- crystal death 부재
- duration 급락
- KDA/minion 동시 붕괴
- frame 수 부족
- `max_death_header_ts - max_player_death_ts` 큰 차이
- broader replay audit 기준으로는 unknown이 `17 -> 0`까지 줄었다
- 현재 56 replay는 `complete_confirmed 53`, `incomplete_confirmed 3`으로 모두 분류된다

필요한 실험:
- broader replay 풀 바깥 새 replay가 들어올 때 false positive가 없는지 지속 검증
- 현재 incomplete 3개 외의 short/debug replay family가 더 있는지 inventory 확장 시 재확인

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
- 즉 immediate OCR backlog는 0개다

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
