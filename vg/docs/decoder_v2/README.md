# Decoder V2 Docs

이 디렉터리는 `decoder_v2`의 정식 문서 세트다.

## 목표

- 전적검색 시스템에 필요한 필드를 프로토콜 수준에서 증명한다.
- 직접 저장된 값과 추론된 값을 분리한다.
- fixture 기반 검증 없이 production claim을 하지 않는다.

## 문서 안내

- `architecture.md`
  - v2의 계층 구조와 책임 분리
- `protocol-registry.md`
  - 바이트 오프셋 / 이벤트 헤더 카탈로그
- `claim-ledger.md`
  - 의미 주장과 현재 판정
- `validation-matrix.md`
  - fixture 기준 성능 수치
- `open-questions.md`
  - 아직 모르는 것과 다음 실험

## 현재 상태 요약

- production-ready에 가장 가까운 필드
  - hero
  - team grouping
  - entity id
- strong but still derived
  - winner on complete fixtures
  - kills / deaths / assists on complete fixtures
- not production-ready
  - duration exact value
  - minion kills
  - incomplete replay handling

## Current CLI

- safe output
  - `python -m vg.decoder_v2.decode_match <replay.0.vgr> --format safe-json`
- debug output
  - `python -m vg.decoder_v2.decode_match <replay.0.vgr> --format debug-json`
- fixture validation
  - `python -m vg.decoder_v2.validation --truth vg/output/tournament_truth.json`
- sparse residual signal research
  - `python -m vg.decoder_v2.residual_signal_research --truth vg/output/tournament_truth.json -o residual.json`
- same-frame minion window research
  - `python -m vg.decoder_v2.minion_window_research <replay.0.vgr> --truth vg/output/tournament_truth.json -o window.json`
- truth coverage inventory
  - `python -m vg.decoder_v2.truth_inventory --truth vg/output/tournament_truth.json`
- batch conservative export
  - `python -m vg.decoder_v2.batch_decode <replay_root> -o batch.json`
- truth stub generation
  - `python -m vg.decoder_v2.truth_stubs --truth vg/output/tournament_truth.json -o stubs.json`
- truth audit
  - `python -m vg.decoder_v2.truth_audit --truth vg/output/tournament_truth.json --ocr <ocr_truth.json> -o audit.json`
- index-safe export
  - `python -m vg.decoder_v2.index_export <replay_root> -o index.json`

## Safe Output Policy

- `claim_status`는 과학적 판정이다.
- `accepted_for_index`는 제품 정책이다.
- 즉 `strong`이라도 incomplete replay면 `accepted_for_index = false`일 수 있다.

## Truth Coverage Snapshot

- 현재 로컬 replay 디렉터리: 56개
- truth로 연결된 디렉터리: 11개
- truth coverage: 약 19.6%
- result image가 있는 디렉터리: 11개

즉 fixture 기반 검증은 tournament set에 강하게 걸려 있지만,
전체 로컬 replay 풀 대비 truth coverage는 아직 낮다.
