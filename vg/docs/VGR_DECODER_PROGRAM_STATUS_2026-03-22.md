# VGR Decoder Program Status 2026-03-22

이 문서는 현재 VGR 파싱/디코딩 작업의 목표, 시도한 접근, 완료 범위, 남은 리스크를 한 번에 정리한 상태 문서다.

## 1. 최종 목표

최종 목표는 다음과 같다.

- Vainglory replay `.vgr`에서 전적검색 시스템에 필요한 데이터를 안정적으로 추출한다.
- “대충 맞는 추정치”가 아니라, 필드별로 어떤 바이트/이벤트에서 값이 나오는지 설명 가능한 디코더를 만든다.
- unsupported replay, incomplete replay, 아직 증명되지 않은 field는 억지로 채우지 않고 명시적으로 거부한다.

즉 목표는 단순히 “현재 fixture에 잘 맞는 Python 스크립트”가 아니라:

- 프로토콜 수준으로 설명 가능한 파서
- 제품에 넣어도 되는 field와 아직 보류해야 하는 field를 구분하는 정책
- truth 부족과 truth 품질 문제까지 같이 관리하는 검증 체계

를 만드는 것이다.

## 2. 왜 기존 방식만으로는 부족했는가

기존 `UnifiedDecoder` 중심 구조는 연구 성과는 많았지만 다음 문제가 있었다.

- direct offset field와 heuristic field가 같은 층에서 섞여 있었다.
- incomplete replay를 별도 정책 없이 해석했다.
- truth 기반 검증 코드 일부가 실제 decoder 정확도를 가리는 구조였다.
- 실험 스크립트와 production 후보 로직의 경계가 약했다.

그래서 현재 방향은:

- low-level proven fact는 유지
- 통합 디코더와 검증 정책은 `decoder_v2`로 분리

라는 `strangler rewrite`에 가깝다.

## 3. 지금까지 시도한 것

### A. 기존 core/tooling 복구

실행 경로 자체가 깨진 부분부터 복구했다.

- `vg/core/vgr_database.py`
  - package import fallback 추가
  - duplicate replay import 시 `lastrowid` 오염 제거
  - parser의 실제 field명(`duration_seconds`, `winner`)에 맞춤
- `vg/core/vgr_parser.py`
  - `.vgr_truth` 상대 import fallback 추가
- `vg/core/replay_extractor.py`
  - 존재하지 않는 hero matcher API 호출 제거
- `vg/core/export_matches.py`
  - heterogeneous row CSV export 복구
  - `--csv-only` 실제 반영
- `vg/tools/replay_batch_parser.py`
  - `map_mode` drift 수정
- `vg/ocr/tournament_ocr.py`
  - pair 0개 실패 처리
  - `.png/.jpg/.jpeg` 지원

### B. analysis/validation 정리

연구 스크립트 중 현재 검증에 직접 필요한 것들을 import-safe하게 정리하고, truth 기반 검증 경로를 바로잡았다.

- `vg/analysis/decode_tournament.py`
  - `decode_with_truth()` 대신 `decode()` 기준으로 검증
  - fuzzy name matching 추가
- `vg/analysis/generate_report.py`
  - import side effect 제거
- `vg/analysis/minion_kill_validation.py`
  - 현재 parser/KDADetector API 기준으로 재작성
- `vg/analysis/cross_validate_death_codes.py`
  - 실제 parser output shape 기준으로 수정
- `vg/analysis/test_kda_detector.py`
  - import-safe 정리

### C. `decoder_v2` foundation 구축

새 디코더 기반을 별도 패키지로 만들었다.

- registry / claim ledger / field status
- raw player block parser
- replay completeness assessment
- conservative duration estimate
- raw credit event parser
- raw player event parser
- conservative winner/KDA decode
- safe single-match export
- safe batch export
- index-safe export

핵심 원칙:

- direct field는 evidence 기반으로만 `accepted`
- derived field는 completeness gate를 통과한 경우만 `accepted`
- 아직 partial인 field는 safe output에서 `withheld`

### D. truth/coverage 파이프라인

truth가 부족하다는 가설을 코드로 검증했다.

- `truth_inventory.py`
  - local replay 디렉터리 대비 truth coverage 측정
- `labeling_backlog.py`
  - immediately-labelable / manifest-only / raw-only 분리
- `truth_stubs.py`
  - truth 없는 replay에 대한 prefilled stub 생성
- `truth_audit.py`
  - current truth vs OCR truth vs safe decode 비교

### E. minion research

현재 가장 큰 미해결 항목인 minion kill을 여러 단계로 팠다.

1. baseline signal 비교
- `0x0E@1.0`
- `0x0F@1.0`
- `0x0D_total`
- additive 조합

2. action `0x04` research
- replay 단위 payload 분포 조사
- complete fixture 전체에서 value bucket count 비교

3. sparse residual research
- `truth - 0x0E baseline` residual만 따로 평가
- `MAE`뿐 아니라 precision/recall/F1/exact-match 추가

4. same-frame minion window research
- `0x0E/0x0F` 주변 header enrichment
- same-frame credit pattern enrichment

## 4. 현재까지 완료된 것

### A. 직접 저장된 field

현재 fixture 기준으로 사실상 확정된 영역:

- player entity id
- hero id
- team byte grouping
- hero/team/entity parsing

현재 기준 수치:

- hero: `109/109 = 100.0%`
- team: `109/109 = 100.0%`

### B. complete replay 기준 strong field

현재 tournament complete fixture 기준 strong한 영역:

- winner: `10/10 = 100.0%`
- kills: `98/99 = 99.0%`
- deaths: `97/99 = 98.0%`
- assists: `97/99 = 98.0%`

이 field들은 `decoder_v2` safe output에서 complete-confirmed replay에 한해 index-safe 후보로 취급한다.

### C. incomplete replay gate

현재 tournament fixture에서는 completeness gate가 다음처럼 동작한다.

- `complete_confirmed`: 10
- `incomplete_confirmed`: 1

즉 incomplete replay는 now-safe 정책으로 winner/K/D/A를 withholding할 수 있다.

### D. truth coverage 측정

현재 local replay 풀 대비 truth coverage:

- replay directories: `56`
- truth-covered: `11`
- missing: `45`
- coverage: `19.6%`

즉 decoder 연구는 진전됐지만, 검증 커버리지는 여전히 좁다.

## 5. 아직 미완료인 것

### A. duration exact decode

현재 duration은 exact field가 아니다.

- exact match: `0/11`
- complete fixture MAE: `17.4s`

즉 현재는 approximate field이며, production DB에 그대로 넣으면 안 된다.

### B. minion kill exact decode

현재 baseline 결론:

- `0x0E@1.0`와 `0x0F@1.0`는 가장 강한 single signal
- 하지만 complete fixture match 6에서 체계적 undercount가 남는다
- `0x0E + 0x0F` 같은 단순 additive 해법은 틀린다

추가 결론:

- action `0x04` bucket은 `MAE`만 보면 좋아 보이지만 sparse residual 기준으로는 overfit 가능성이 높다
- match 6 same-frame window에서는 `28 04 3F`, `08 04 2C`, `18 04 1C`, 일부 `0x02`/`0x08`/`0x00` family가 positive residual 쪽에 더 자주 붙는다
- 다만 아직 match 6 중심 evidence라 cross-fixture generalization이 필요하다

즉 minion은 아직 `withheld`가 맞다.

### C. truth 자체의 품질

OCR truth audit 결과:

- score mismatch matches: `8/11`
- player-level minion mismatches: `47/110`
- K/D/A mismatch는 상대적으로 작음

즉 OCR는 score/minion ground truth로 바로 승격하면 안 된다.

## 6. 지금 제품에 넣어도 되는 것과 아닌 것

### 지금 safe하게 index에 넣을 수 있는 것

- replay identity
- player names
- hero
- entity id
- team grouping
- complete-confirmed replay의 winner
- complete-confirmed replay의 kills/deaths/assists

### 아직 넣으면 안 되는 것

- duration exact value
- minion kills
- incomplete replay의 derived stats
- OCR score/minion을 그대로 ground truth로 간주한 값

## 7. 다음 우선순위

우선순위는 다음 순서가 맞다.

1. minion same-frame enriched signal을 complete fixture 전체로 확장 검증
2. duration exact match-end signal 별도 분리
3. truth source 확장
4. broader replay pool에서 completeness rule 검증

## 8. 현재 판단

현재 프로젝트는 “기존 decoder를 무조건 보수하는 단계”를 지나서,

- 실행 경로 복구
- 검증 경로 복구
- conservative product policy 도입
- `decoder_v2` foundation 구축
- truth coverage/quality 계량화
- minion research를 residual/window 단계까지 확장

까지는 완료된 상태다.

하지만 전적검색 시스템을 위한 “100% 신뢰 가능한 전체 stat decode”는 아직 아니다.

현재 가장 정확한 표현은 다음과 같다.

- parser/direct field는 강하다
- complete replay 기준 winner/K/D/A는 꽤 강하다
- minion/duration은 아직 연구 대상이다
- truth coverage와 truth quality를 동시에 확장해야 한다
