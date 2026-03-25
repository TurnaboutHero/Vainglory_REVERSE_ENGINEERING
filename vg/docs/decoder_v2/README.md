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
- complete-fixture minion window research
  - `python -m vg.decoder_v2.minion_window_fixture_research --truth vg/output/tournament_truth.json -o complete-window.json`
- target-vs-baseline minion outlier compare
  - `python -m vg.decoder_v2.minion_outlier_compare --truth vg/output/tournament_truth.json --replay-name <replay_name> -o outlier.json`
- same-hero minion outlier compare
  - `python -m vg.decoder_v2.minion_hero_compare --truth vg/output/tournament_truth.json --replay-name <replay_name> -o hero-compare.json`
- same-hero minion outlier score
  - `python -m vg.decoder_v2.minion_hero_outlier_score --truth vg/output/tournament_truth.json --replay-name <replay_name> -o hero-score.json`
- action-family minion outlier compare
  - `python -m vg.decoder_v2.minion_pattern_family_compare --truth vg/output/tournament_truth.json --replay-name <replay_name> -o family-compare.json`
- action-value minion compare for one family
  - `python -m vg.decoder_v2.minion_action_value_compare --truth vg/output/tournament_truth.json --replay-name <replay_name> --action 0x02 -o action-compare.json`
- action-family cluster compare
  - `python -m vg.decoder_v2.minion_action_cluster_compare --truth vg/output/tournament_truth.json --replay-name <replay_name> --action 0x02 -o action-clusters.json`
- action-family context profile
  - `python -m vg.decoder_v2.action02_value_context_profile --truth vg/output/tournament_truth.json -o action02-context.json`
- action-family sharing profile
  - `python -m vg.decoder_v2.action02_sharing_profile --truth vg/output/tournament_truth.json -o action02-sharing.json`
- action02 hero affinity
  - `python -m vg.decoder_v2.action02_hero_affinity --truth vg/output/tournament_truth.json -o action02-heroes.json`
- action-family subfamily summary
  - `python -m vg.decoder_v2.action02_subfamily_summary --truth vg/output/tournament_truth.json --replay-name <replay_name> -o action02-subfamilies.json`
- target replay provenance trace
  - `python -m vg.decoder_v2.minion_action_provenance --truth vg/output/tournament_truth.json --replay-name <replay_name> --action 0x02 -o provenance.json`
- minion outlier risk report
  - `python -m vg.decoder_v2.minion_outlier_risk_report --truth vg/output/tournament_truth.json -o risk.json`
- minion acceptance gate research
  - `python -m vg.decoder_v2.minion_acceptance_gate_research --truth vg/output/tournament_truth.json -o acceptance-gates.json`
- minion series profile
  - `python -m vg.decoder_v2.minion_series_profile --truth vg/output/tournament_truth.json -o series.json`
- minion same-series peer compare
  - `python -m vg.decoder_v2.minion_series_peer_compare --truth vg/output/tournament_truth.json --replay-name <replay_name> -o series-peers.json`
- minion same-series bucket rule research
  - `python -m vg.decoder_v2.minion_series_bucket_rule_research --truth vg/output/tournament_truth.json -o series-bucket-rules.json`
- minion self-vs-team linkage compare
  - `python -m vg.decoder_v2.minion_action_self_vs_team --truth vg/output/tournament_truth.json --replay-name <replay_name> --action 0x02 -o self-vs-team.json`
- minion relation compare
  - `python -m vg.decoder_v2.minion_action_relation_compare --truth vg/output/tournament_truth.json --replay-name <replay_name> --action 0x02 -o relation.json`
- truth coverage inventory
  - `python -m vg.decoder_v2.truth_inventory --truth vg/output/tournament_truth.json`
- truth source priority
  - `python -m vg.decoder_v2.truth_source_priority --truth vg/output/tournament_truth.json -o truth-priority.json`
- batch conservative export
  - `python -m vg.decoder_v2.batch_decode <replay_root> -o batch.json`
- broader completeness audit
  - `python -m vg.decoder_v2.completeness_audit -o completeness-audit.json`
- completeness outlier compare
  - `python -m vg.decoder_v2.completeness_outlier_compare --replay-name <replay_name> -o completeness-outlier.json`
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
