# Codex Review 2026-03-18

Claude Code로 구현된 현재 저장소를 Codex 관점에서 전체 재검토한 결과다.
이번 문서는 "실제로 깨지는 경로", "구조적으로 위험한 패턴", "수정 우선순위"를 남기는 데 목적이 있다.

## 범위

- `vg/core`
- `vg/tools`
- `vg/ocr`
- 루트의 테스트 스크립트
- `vg/analysis` 223개 모듈의 import/runtime 안전성, 하드코딩 경로, 검증 스크립트 품질

비코드 산출물(`vg/output`, docs, JSON 결과물)은 구조적 영향이 있는 경우만 확인했고 내용 자체는 전수 검토하지 않았다.

## 검증 방식

- 정적 코드 리뷰
- package import sweep
- 대표 CLI 실행 확인
- analysis 모듈 import side effect 재현
- 자동 테스트 탐지 상태 확인
- 문법 검증: `python -m compileall vg test_win_loss_detector.py`

## 요약

| Severity | 항목 | 영향 |
|---|---|---|
| HIGH | `vgr_database.py` duplicate import 처리 오류 | 중복 replay import 시 player row가 잘못된 match에 연결될 수 있음 |
| HIGH | `replay_extractor.py`가 없는 HeroMatcher API 호출 | 정상 replay 경로에서 런타임 예외 |
| HIGH | `vg.core.vgr_database` 패키지 import 실패 | `python -m` 및 라이브러리 import 불가 |
| HIGH | `vgr_parser.py` truth fallback 누락 | package import 기준 truth 기능 비활성화 |
| HIGH | `vg.analysis` import side effect | import만으로 분석 실행, stdout 발생, 파일 생성 |
| HIGH | 일부 analysis 스크립트가 존재하지 않는 심볼 참조 | 모듈 import/실행 즉시 실패 |
| MEDIUM | export 계층 contract 불일치 | partial truth CSV export 실패, `--csv-only` 무효 |
| MEDIUM | tools 문서/CLI drift | README와 실제 인터페이스가 다름 |
| MEDIUM | MITM capture 민감정보 저장 및 메모리 누적 | 보안/성능 리스크 |
| MEDIUM | 자동 회귀 테스트 부재 | 변경 안정성 낮음 |

## 상세 Findings

### 1. HIGH - DB import가 중복 replay에서 데이터 오염을 만들 수 있음

대상:
- `vg/core/vgr_database.py`

핵심 문제:
- `INSERT OR IGNORE` 직후 `cursor.lastrowid`를 성공 여부 판단에 사용한다.
- SQLite에서는 insert가 무시돼도 `lastrowid`가 이전 성공 insert 값을 유지할 수 있다.
- 그 상태에서 `match_players` insert를 계속하면 현재 replay의 player row가 이전 match에 잘못 연결될 수 있다.

추가 문제:
- 같은 코드가 `match_info.get('duration')`, `match_info.get('winning_team')`를 읽는데,
  실제 parser output은 `duration_seconds`, `winner`를 사용한다.
- 즉 import가 성공해도 match 메타데이터 일부는 조용히 유실된다.

권장 수정:
1. `INSERT OR IGNORE` 뒤에는 `lastrowid`를 신뢰하지 말 것
2. `SELECT id FROM matches WHERE replay_name=?`로 실제 `match_id`를 재조회할 것
3. 이미 존재하는 replay면 player insert를 건너뛸 것
4. parser 필드명과 DB import 필드명을 맞출 것

### 2. HIGH - `ReplayExtractor`는 현재 정상 경로에서 런타임으로 깨짐

대상:
- `vg/core/replay_extractor.py`
- `vg/core/hero_matcher.py`

핵심 문제:
- `ReplayExtractor._match_heroes_to_players()`가 `HeroMatcher.detect_heroes_with_probes()`를 호출한다.
- 그런데 `HeroMatcher`에는 그 메서드가 정의되어 있지 않다.
- 실제 확인 결과 `hasattr(HeroMatcher, 'detect_heroes_with_probes') == False`.

영향:
- hero matching까지 도달하는 extraction 경로는 즉시 `AttributeError`로 실패한다.

권장 수정:
- `HeroMatcher.detect_heroes()` 또는 `detect_heroes_from_blocks()`로 호출 대상을 바꾸거나
- 누락된 메서드를 실제 구현과 함께 복구할 것

### 3. HIGH - `vg.core.vgr_database`는 패키지 import 자체가 깨져 있음

대상:
- `vg/core/vgr_database.py`

핵심 문제:
- `from vgr_parser import VGRParser`를 하드코딩해 두었다.
- 패키지 경로(`vg.core.vgr_database`)로 import하면 이 import가 깨진다.

실제 확인:
- `python -c "import vg.core.vgr_database"` 실패
- `python -m vg.core.vgr_database init --db NUL` 실패
- 에러: `ModuleNotFoundError: No module named 'vgr_parser'`

권장 수정:
- 다른 core 모듈처럼 상대 import fallback 구조를 추가할 것

### 4. HIGH - package import 기준 truth 기능이 비활성화됨

대상:
- `vg/core/vgr_parser.py`
- `vg/core/vgr_truth.py`

핵심 문제:
- `vgr_parser.py`는 `from vgr_truth import load_truth_data`만 시도하고,
  실패하면 `TRUTH_AVAILABLE = False`로 끝낸다.
- 같은 디렉터리에 `vgr_truth.py`가 존재하지만 `.vgr_truth` fallback이 없다.

실제 확인:
- `from vg.core import vgr_parser as m; print(m.TRUTH_AVAILABLE)` -> `False`
- `vg.core.vgr_truth` 자체는 import 가능

영향:
- library 경로로 parser를 사용할 때 `--truth`와 auto-truth가 사실상 꺼진다.

권장 수정:
- mapping / hero matcher import와 동일하게 상대 import fallback을 추가할 것

### 5. HIGH - `vg.analysis` 아래 다수 스크립트가 import-safe하지 않음

대상:
- `vg/analysis/full_kda_parser_v2.py`
- `vg/analysis/generate_report.py`
- `vg/analysis` 전반

핵심 문제:
- import만으로 실제 분석이 실행되고, stdout이 발생하고, 결과 파일을 생성하는 모듈이 패키지 내부에 섞여 있다.
- 대표적으로 `import vg.analysis.full_kda_parser_v2`만으로 로컬 replay를 읽고 `vg/output/full_kda_v2.json`을 쓴다.
- `import vg.analysis.generate_report`는 `.omc/scientist/reports/...`에 보고서를 만든다.

정량 확인:
- `vg/analysis` 223개 중 `__main__` 가드 없는 파일 32개
- 절대 로컬 경로 또는 `sys.path.insert` 의존 파일 186개
- import sweep 중 stdout side effect가 확인된 모듈 13개

영향:
- 패키지 탐색
- 자동 문서화
- 테스트 수집
- import 기반 재사용

모두 부작용을 일으킬 수 있다.

권장 수정:
1. 실행 본문을 `main()`으로 옮길 것
2. `if __name__ == '__main__':` 가드 아래에서만 실행할 것
3. 로컬 절대경로와 `sys.path.insert`를 인자/환경변수 기반으로 치환할 것

### 6. HIGH - 일부 analysis 스크립트는 현재 코드베이스와 API가 맞지 않아 실행 불가

대상:
- `vg/analysis/minion_kill_validation.py`
- `vg/analysis/cross_validate_death_codes.py`

핵심 문제 A:
- `minion_kill_validation.py`는 존재하지 않는 `identify_hero_mapping`를 import한다.
- `python -c "import vg.analysis.minion_kill_validation"`로 즉시 `ImportError` 재현 가능.

핵심 문제 B:
- `cross_validate_death_codes.py`는 `VGRParser.parse()`의 `data['players']`를 dict 목록으로 가정한다.
- 실제 parser는 그 자리에 이름 문자열 목록을 넣는다.
- 그래서 player entity 추출이 실패하고, 코드가 `range(50000, 60000)` fallback으로 내려가면서 분석 신뢰도가 무너진다.

권장 수정:
- 현재 `VGRParser` / `HeroMatcher` API에 맞게 스크립트를 갱신할 것
- 실패를 감추는 fallback 대신 명시적으로 abort할 것

### 7. MEDIUM - export 계층의 contract가 깨져 있음

대상:
- `vg/core/export_matches.py`

핵심 문제 A:
- `match_to_csv_rows()`는 truth 컬럼을 row마다 조건부로 추가한다.
- `export_csv()`는 첫 row key만 header로 사용한다.
- partial truth가 섞이면 `ValueError`가 발생한다.

핵심 문제 B:
- `--csv-only` 옵션은 파싱만 하고 실제 분기에서는 전혀 사용하지 않는다.
- 단일 export와 batch export 모두 JSON을 계속 쓴다.

권장 수정:
1. CSV header를 모든 row key union으로 만들거나 고정 스키마를 강제할 것
2. `args.csv_only`를 실제 출력 분기에 반영할 것

### 8. MEDIUM - tools 문서와 실제 CLI가 서로 다름

대상:
- `vg/tools/replay_batch_parser.py`
- `vg/tools/README.md`

핵심 문제:
- 코드는 존재하지 않는 `map_mode` 키를 읽어서 map 정보가 사실상 항상 `unknown`이다.
- README에는 `--format`, `--detect-heroes`, `--summary-only` 같은 옵션이 적혀 있지만 실제 CLI는 지원하지 않는다.

실제 확인:
- `python vg/tools/replay_batch_parser.py --help` -> `replay_dir`, `--output`만 표시
- `python vg/tools/replay_batch_parser.py . --format csv-heroes` -> `unrecognized arguments`

권장 수정:
- `match_info.map_name`를 사용하도록 코드 수정
- 문서와 CLI 중 하나를 기준으로 계약을 다시 맞출 것

### 9. MEDIUM - MITM capture 도구는 민감정보 저장과 장시간 세션 성능 문제가 있음

대상:
- `vg/tools/mitm_capture.py`

핵심 문제 A:
- request/response 헤더와 body를 무가공으로 저장한다.
- `Authorization`, cookie, token 류가 그대로 디스크에 남을 수 있다.

핵심 문제 B:
- 모든 capture를 메모리에 계속 쌓고,
  10건마다 전체 history를 새 JSON 파일로 다시 쓴다.
- 장시간 세션에서 메모리 증가와 과도한 재쓰기 비용이 생긴다.

권장 수정:
1. 민감 헤더를 redact할 것
2. body는 whitelist 또는 opt-in 저장으로 바꿀 것
3. JSONL/NDJSON append 또는 batch rotation 방식으로 바꿀 것

### 10. MEDIUM - 자동 회귀 테스트가 사실상 없음

대상:
- 루트 `test_win_loss_detector.py`
- `vg/analysis/test_kda_detector.py`
- 저장소 전체 테스트 체계

확인 결과:
- `python -m unittest discover -v` -> `Ran 0 tests`
- `python -m pytest -q` -> `No module named pytest`
- 테스트처럼 보이는 파일들은 모두 하드코딩된 로컬 경로를 쓰는 수동 스크립트다

의미:
- `vgr_parser`, `unified_decoder`, `export_matches`, `vgr_database` 같은 핵심 경로를 보호하는 자동 회귀망이 없다.

권장 수정:
- fixture 기반 unit/integration test를 핵심 경로부터 추가할 것

## 검증 로그

- `python -m compileall vg test_win_loss_detector.py` 통과
- `python -c "import vg.core.vgr_database"` 실패
- `python -m vg.core.vgr_database init --db NUL` 실패
- `python -c "from vg.core import vgr_parser as m; print(m.TRUTH_AVAILABLE)"` -> `False`
- `python -c "import vg.analysis.generate_report"` -> `.omc/scientist/reports/...` 생성
- `python -c "import vg.analysis.full_kda_parser_v2"` -> import만으로 분석 실행 및 `vg/output/full_kda_v2.json` 기록
- `python -c "import vg.analysis.minion_kill_validation"` 실패
- `python vg/ocr/verify_tournament_truth.py --truth vg/output/tournament_truth.json --parsed vg/output/tournament_parsed.json --max-details 3` 통과
- `python vg/tools/replay_batch_parser.py . --format csv-heroes` 실패

## 권장 작업 순서

1. `vg/core/vgr_database.py` import 경로와 duplicate import 정합성 수정
2. `vg/core/replay_extractor.py`의 HeroMatcher 호출 복구
3. `vg/core/vgr_parser.py` truth fallback 추가
4. `vg/core/export_matches.py`의 CSV/header/`--csv-only` 복구
5. `vg/analysis`의 import-safe 정리
6. 핵심 경로 자동 테스트 추가

## 결론

현재 저장소는 연구/실험 산출물이 풍부하고, 핵심 reverse-engineering 지식도 많이 축적되어 있다.
다만 "라이브러리/도구로 재사용 가능한 상태"라는 기준에서는 아직 정리해야 할 부분이 많다.

특히 `core` 패키징 정합성, `analysis` import-safe, export/test 계층은 먼저 손보는 것이 맞다.
