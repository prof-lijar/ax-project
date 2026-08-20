# RAG Retrieval-Quality Evaluation Set

Date: 2026-08-20

## Purpose

This file defines a fixed, source-grounded retrieval benchmark for comparing
future chunking or retrieval configurations. It contains 20 questions drawn
only from these two already-ingested real project documents:

- `analysis_wardevaluation_recovery_data_lineage.md`
- `광명시 AI.pdf`

This phase defines the benchmark only. No retrieval was run and neither document
was re-ingested while creating this file.

## Ground-truth and scoring rules

- Each expected answer must be explicitly supported by the named source.
- The ground-truth field contains a short evidence excerpt and section reference.
- Retrieval rank is measured as the first returned chunk containing sufficient
  evidence to answer the question.
- Top-k results should be evaluated for evidence sufficiency, not merely shared
  vocabulary.
- Preserve these exact question strings for future comparisons.
- Record retrieval results separately from this fixed definition so ground truth
  is not rewritten after observing rankings.

The earlier manual baseline retained question IDs, per-question ranks, and
aggregate results, but the existing documentation did not retain all ten
verbatim question strings. Therefore, questions 01–05 for each source preserve
the earlier five-per-source structure and known themes where possible; the
documented 2024-participant question is retained explicitly. Questions 06–10
test distinct facts and retrieval challenges. Historical ranks are not
retroactively assigned to any newly fixed wording unless the original query is
known to match.

## Evaluation questions — Recovery data-lineage Markdown

| ID | Set | Category | Question | Expected answer | Ground-truth evidence / reference |
| --- | --- | --- | --- | --- | --- |
| MD-Q01 | Baseline-aligned | Broad semantic | 과거 ward evaluation을 복구할 때 구현의 최종 source of truth는 무엇인가요? | `analysis_wardevaluation_recovery_data_lineage.md`에 정의된 Recovery 정책이 최종 source of truth이며, 기존 Production 문서는 참고 자료다. | “이 문서의 Recovery 정책이 구현의 최종 source of truth다.” — §1 문서 목적 |
| MD-Q02 | Baseline-aligned | Specific rule/process | 동일 ward의 최신 daily timestamp에 여러 IMEI 문서가 있으면 last_vital_sign_timestamp를 어떻게 선택하나요? | 최신 timestamp의 모든 IMEI 후보에서 null이 아닌 vital 시각을 정규화한 뒤 가장 최신 값을 선택하며, 모두 null이면 `None`을 사용한다. | “그중 가장 최신 값을 … 선택한다”, “모든 후보가 null이면 `None`” — §10 |
| MD-Q03 | Baseline-aligned | Exact entity/name | Recovery 결과의 유일한 저장 대상과 재실행 시 충돌 처리 기준은 무엇인가요? | 유일한 destination은 `archive.analysis_wardevaluation`이며, `(ward_id, evaluated_at)` 충돌 시 `DO NOTHING`으로 기존 행을 바꾸지 않는다. | “Destination은 `archive.analysis_wardevaluation` 하나”, unique key와 `DO NOTHING` — §6, §18 |
| MD-Q04 | Baseline-aligned | Boundary/threshold | Recovery evaluated_at 시계열은 시작·종료 시각과 5분 경계를 어떻게 처리하나요? | start와 end를 포함하고 5분씩 증가시키되 초·마이크로초만 0으로 정규화한다. 시작 분을 5의 배수로 floor하지 않아 시작이 `:03`이면 `:03, :08, :13...`이다. | `start <= evaluated_at <= end`, “시작 분… 별도 floor하지 않는다” — §8 |
| MD-Q05 | Baseline-aligned | Specific rule/process | 자동 주시 전환의 조건과 생성되는 두 행은 무엇인가요? | MORNING 정상 계산이 `DANGER`, 누적 전 `danger_counts >= 7`, 마지막 DANGER 날짜가 현재 KST 날짜보다 이전일 때 전환한다. 원래 DANGER 행과 `+1초`의 모든 점수 70인 CAUTION 행을 만든다. | 조건 3개와 “원래 `DANGER` row”, “`evaluated_at + 1초`” — §15 |
| MD-Q06 | New | Exact entity/name | Recovery 평가 대상 ward_id는 어느 source와 query 의미로 선정하나요? | `archive.resources_measurement`에서 null이 아닌 distinct `ward_id`를 정렬해 선정하며, `ansimk.resources_location`이나 현재 설치 상태는 사용하지 않는다. | `SELECT DISTINCT ward_id ... WHERE ward_id IS NOT NULL` — §7 |
| MD-Q07 | New | Boundary/threshold | score 25, 26, 50, 51, 75, 76은 각각 어떤 risk level인가요? | 25 DANGER, 26 ALERT, 50 ALERT, 51 CAUTION, 75 CAUTION, 76 STABLE이다. | 경계 검증값 목록 — §12 Risk level |
| MD-Q08 | New | Boundary/threshold | `is_out=True`일 때 마지막 반응 후 정확히 30분인 경우와 30분을 초과한 경우의 처리가 어떻게 다른가요? | 30분 초과면 모든 점수 70과 `user_is_out=True`를 반환한다. 정확히 30분 이내면 메모리 `is_out=False`로 바꾸고 일반 계산으로 진행한다. | “30분을 초과하면…70”, “정확히 30분 이내이면…일반 계산” — §14 |
| MD-Q09 | New | Specific rule/process | 조회 범위에 device-daily 문서가 하나도 없으면 점수와 상태값은 어떻게 설정되나요? | overall과 다섯 component 점수를 모두 30으로 설정하고 `device_has_signal=False`, `user_is_out=False`로 둔다. | “모든 점수를 30”, 두 boolean 값 — §11 |
| MD-Q10 | New | Specific rule/process | 같은 KST 날짜에 DANGER가 여러 번 발생하면 danger_counts는 어떻게 누적되며 자동 주시 +1초 행은 포함되나요? | 해당 날짜의 첫 DANGER만 count를 1 증가시키고 같은 날 추가 DANGER는 증가시키지 않는다. 자동 주시 `+1초` CAUTION 행은 DANGER 누적 대상이 아니다. | “첫 DANGER일 때만”, “같은 날짜의 추가 DANGER는…않는다” — §16 |

## Evaluation questions — Gwangmyeong AI/IoT PDF

| ID | Set | Category | Question | Expected answer | Ground-truth evidence / reference |
| --- | --- | --- | --- | --- | --- |
| PDF-Q01 | Baseline-aligned | Broad semantic | 광명시 AI·IoT 기반 어르신 건강관리사업은 어떤 사업인가요? | 건강관리가 필요한 65세 이상 어르신에게 스마트 건강측정기기를 제공하고 ‘오늘건강’ 앱으로 광명시보건소가 관리하는 비대면 건강관리사업이다. | 사업 정의 — §1 사업 개요 |
| PDF-Q02 | Baseline-aligned | Specific rule/process | 이 사업의 대상자는 누구이며 어떤 사람이 우선 고려되나요? | 광명시 거주 65세 이상 중 노쇠·만성질환 예방관리 또는 건강행태 개선이 필요한 사람이며, 통합돌봄 연계 대상자, 수급자·차상위계층, 관리되지 않는 만성질환자와 위험군 등이 우선 고려된다. | 대상과 우선 고려 대상 — §2 |
| PDF-Q03 | Baseline-aligned | Specific rule/process | 사업 신청 후 6개월 비대면 관리까지 어떤 순서로 진행되나요? | 신청·선별, 방문간호사 건강 스크리닝, 건강군·전허약군·허약군 등 분류, 필요한 디바이스와 월별 미션 제공, 6개월 비대면 관리 순서다. | 운영 절차 도식 — §3 운영 방식 |
| PDF-Q04 | Baseline-aligned | Specific rule/process | 참여자에게 건강측정기기는 어떻게 제공되며 적극 참여 후에는 어떻게 되나요? | 건강 상태와 위험요인에 따라 스마트밴드·체중계·혈압계·혈당계 중 1인당 2종을 선별 대여하고, 6개월간 적극 참여한 대상자에게 대여기기를 증정한다. | “1인당 2종”, “6개월간…증정” — §4 |
| PDF-Q05 | Baseline-aligned | Numeric/year | 2024년 광명시 AI·IoT 어르신 건강관리사업 참여자 수는 몇 명으로 보고됐나요? | 920명이다. | “2024년 920명” — §6 사업 운영실적 |
| PDF-Q06 | New | Numeric/year | 광명시는 서비스를 언제 시작했고 2022년 참여자는 몇 명이었나요? | 2021년 11월 15일 시작했고, 2022년 참여자는 187명이었다. | 시작일과 2022년 수치 — §1, §6 |
| PDF-Q07 | New | Exact entity/name | 광명시에서 이 사업을 담당하는 부서와 주요 업무는 무엇인가요? | 광명시보건소 보건정책과 생명존중팀이 담당하며, 사업계획·예산, 참여자 모집·등록, 사업인력 및 대상자 관리를 수행한다. | 담당 부서와 업무 — §2 |
| PDF-Q08 | New | Boundary/threshold | 오늘건강 앱 미접속과 연락 불가가 어느 정도 지속되면 퇴록될 수 있나요? | 1개월 이상 앱에 접속하지 않고 연락도 되지 않을 경우 퇴록될 수 있다. | “1개월 이상…접속하지 않고 연락도 되지 않을 경우” — §5 |
| PDF-Q09 | New | Exact entity/name | ‘오늘건강’ 앱은 광명시가 자체 개발한 앱인가요? 누가 추진한 사업에서 사용하는 앱인가요? | 광명시 자체 개발 앱이 아니며, 보건복지부와 한국건강증진개발원이 추진하는 사업에서 전국 참여 보건소가 공통 사용하는 대상자용 앱이다. | 앱의 개발·운영 주체 설명 — §5 |
| PDF-Q10 | New | Numeric/year | 2025년 참여자 수는 얼마로 보고됐고, 그 수치에는 어떤 해석상 주의점이 있나요? | 2025년 11월 27일 행정사무감사에서 1,198명으로 보고됐다. 정확한 집계 기준일과 연말 최종 실적 여부는 확인되지 않으며 누적 성격일 수 있다. | 2025년 `1,198명`과 주의 문구 — §6 |

## Category breakdown

Each question has one primary category for reporting purposes:

| Category | IDs | Count |
| --- | --- | ---: |
| Broad semantic | MD-Q01, PDF-Q01 | 2 |
| Specific rule/process | MD-Q02, MD-Q05, MD-Q09, MD-Q10, PDF-Q02, PDF-Q03, PDF-Q04 | 7 |
| Boundary/threshold | MD-Q04, MD-Q07, MD-Q08, PDF-Q08 | 4 |
| Exact entity/name | MD-Q03, MD-Q06, PDF-Q07, PDF-Q09 | 4 |
| Numeric/year | PDF-Q05, PDF-Q06, PDF-Q10 | 3 |
| **Total** |  | **20** |

The new questions (06–10 for each source) target facts and sections distinct
from questions 01–05 rather than trivial paraphrases. Several deliberately test
nearby competing evidence: risk/time boundaries, adjacent ward-state rules,
device allocation versus device lists, app participation rules, and multiple
years in one operating-results table.

## Historical baseline context

The first user-performed manual baseline used ten questions—five from each real
document—and measured:

- Top-1 hit rate: 7/10 (70%)
- Top-3 hit rate: 10/10 (100%)
- Top-5 hit rate: 10/10 (100%)

No question missed sufficient supporting evidence within Top-3. Fine-grained
rules and numeric/year questions sometimes placed a broader related chunk ahead
of the exact-answer chunk; the documented 2024 participant-count answer appeared
at rank 3. These are retrieval-ranking precision observations, not ingestion,
extraction, chunking-coverage, embedding, storage, or API failures.

A separate synthetic Markdown observation is not part of this real-document
benchmark: identifier-only query `자주고슴도치MD테스트` missed its containing
chunk within Top-10, while adding meaningful context as
`자주고슴도치MD테스트 별무리 관측소` returned it at rank 1. This remains an
embedding-plus-cosine exact-keyword limitation observation; no lexical search is
implemented.

The ten-question historical sample is too small to claim general retrieval
accuracy. Run the fixed 20 questions unchanged before comparing configurations,
and report both per-question first-evidence ranks and aggregate Top-1/Top-3/Top-5
rates.

## Definition-time deferred-execution checkpoint

The following bullets record the state when this fixed evaluation set was
defined. They are superseded for execution status by the current-configuration
baseline below.

- Retrieval for this 20-question set has not yet been run.
- No source was uploaded or re-ingested while defining it.
- No database row, index, schema, model, vector dimension, chunking parameter,
  API behavior, or runtime resource was changed.

## Current Configuration Baseline Results

### Run conditions

- Date: 2026-08-20
- Retrieval method: `Qwen/Qwen3-Embedding-0.6B` query embedding with
  `prompt_name="query"`, followed by exact pgvector cosine-similarity search.
- Endpoint: read-only `GET /rag/v1/search`
- `top_k`: 5 for every question
- Query handling: all 20 fixed question strings above were submitted unchanged,
  once each. No request failed and no retry was required.
- Runtime: the existing server was not already running, so it was started with
  its current configuration on `127.0.0.1:8765` for this read-only run and then
  stopped normally.
- Ingestion: neither benchmark source was uploaded or re-ingested. No database
  row, schema, or index was changed.
- Scoring: rank is the first returned chunk that alone contains sufficient
  evidence for the complete expected answer. Evidence was not combined across
  multiple returned chunks. `MISS` contributes zero to MRR.

Cosine similarity values below are retrieval scores, not probabilities,
confidence values, or accuracy measurements.

### Per-question results — Recovery data-lineage Markdown

| ID | Source document | Category | Exact query | Expected answer | First sufficient rank | Top-1 | Top-3 | Top-5 | Chunk ID | Cosine similarity | Evaluation note |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | ---: | ---: | --- |
| MD-Q01 | `analysis_wardevaluation_recovery_data_lineage.md` | Broad semantic | 과거 ward evaluation을 복구할 때 구현의 최종 source of truth는 무엇인가요? | `analysis_wardevaluation_recovery_data_lineage.md`에 정의된 Recovery 정책이 최종 source of truth이며, 기존 Production 문서는 참고 자료다. | 1 | Yes | Yes | Yes | 33 | 0.691837120040582 | The first chunk explicitly identifies the Recovery policy as the implementation's final source of truth. |
| MD-Q02 | `analysis_wardevaluation_recovery_data_lineage.md` | Specific rule/process | 동일 ward의 최신 daily timestamp에 여러 IMEI 문서가 있으면 last_vital_sign_timestamp를 어떻게 선택하나요? | 최신 timestamp의 모든 IMEI 후보에서 null이 아닌 vital 시각을 정규화한 뒤 가장 최신 값을 선택하며, 모두 null이면 `None`을 사용한다. | 1 | Yes | Yes | Yes | 39 | 0.829801932119689 | The first chunk contains the candidate-selection, normalization, latest-value, and all-null rules. |
| MD-Q03 | `analysis_wardevaluation_recovery_data_lineage.md` | Exact entity/name | Recovery 결과의 유일한 저장 대상과 재실행 시 충돌 처리 기준은 무엇인가요? | 유일한 destination은 `archive.analysis_wardevaluation`이며, `(ward_id, evaluated_at)` 충돌 시 `DO NOTHING`으로 기존 행을 바꾸지 않는다. | 5 | No | No | Yes | 48 | 0.570755361975513 | A broader chunk naming the unique write target ranked first, but it did not state the required `DO NOTHING` conflict rule. Chunk 48 is the first result containing both the destination/unique-key context and the conflict behavior. |
| MD-Q04 | `analysis_wardevaluation_recovery_data_lineage.md` | Boundary/threshold | Recovery evaluated_at 시계열은 시작·종료 시각과 5분 경계를 어떻게 처리하나요? | start와 end를 포함하고 5분씩 증가시키되 초·마이크로초만 0으로 정규화한다. 시작 분을 5의 배수로 floor하지 않아 시작이 `:03`이면 `:03, :08, :13...`이다. | 1 | Yes | Yes | Yes | 38 | 0.697981127440638 | The first chunk contains the inclusive bounds, five-minute step, normalization, and no-floor rule. |
| MD-Q05 | `analysis_wardevaluation_recovery_data_lineage.md` | Specific rule/process | 자동 주시 전환의 조건과 생성되는 두 행은 무엇인가요? | MORNING 정상 계산이 `DANGER`, 누적 전 `danger_counts >= 7`, 마지막 DANGER 날짜가 현재 KST 날짜보다 이전일 때 전환한다. 원래 DANGER 행과 `+1초`의 모든 점수 70인 CAUTION 행을 만든다. | MISS | No | No | No | — | — | The first chunk contains all three transition conditions but not both generated-row definitions; the second contains the state change and two rows but omits part of the triggering conditions. No single Top-5 chunk supports the complete answer. |
| MD-Q06 | `analysis_wardevaluation_recovery_data_lineage.md` | Exact entity/name | Recovery 평가 대상 ward_id는 어느 source와 query 의미로 선정하나요? | `archive.resources_measurement`에서 null이 아닌 distinct `ward_id`를 정렬해 선정하며, `ansimk.resources_location`이나 현재 설치 상태는 사용하지 않는다. | 3 | No | Yes | Yes | 37 | 0.651470632434433 | The first result broadly lists the archive source, while chunk 37 is the first to contain the distinct/non-null/ordered query meaning and the exclusion of current location state. |
| MD-Q07 | `analysis_wardevaluation_recovery_data_lineage.md` | Boundary/threshold | score 25, 26, 50, 51, 75, 76은 각각 어떤 risk level인가요? | 25 DANGER, 26 ALERT, 50 ALERT, 51 CAUTION, 75 CAUTION, 76 STABLE이다. | 1 | Yes | Yes | Yes | 43 | 0.577695185621574 | The first chunk contains all six exact boundary mappings. |
| MD-Q08 | `analysis_wardevaluation_recovery_data_lineage.md` | Boundary/threshold | `is_out=True`일 때 마지막 반응 후 정확히 30분인 경우와 30분을 초과한 경우의 처리가 어떻게 다른가요? | 30분 초과면 모든 점수 70과 `user_is_out=True`를 반환한다. 정확히 30분 이내면 메모리 `is_out=False`로 바꾸고 일반 계산으로 진행한다. | 1 | Yes | Yes | Yes | 45 | 0.523497514843804 | The first chunk contains both sides of the exact 30-minute boundary. |
| MD-Q09 | `analysis_wardevaluation_recovery_data_lineage.md` | Specific rule/process | 조회 범위에 device-daily 문서가 하나도 없으면 점수와 상태값은 어떻게 설정되나요? | overall과 다섯 component 점수를 모두 30으로 설정하고 `device_has_signal=False`, `user_is_out=False`로 둔다. | 1 | Yes | Yes | Yes | 43 | 0.641615369223309 | The first chunk contains all six score defaults and both boolean values. |
| MD-Q10 | `analysis_wardevaluation_recovery_data_lineage.md` | Specific rule/process | 같은 KST 날짜에 DANGER가 여러 번 발생하면 danger_counts는 어떻게 누적되며 자동 주시 +1초 행은 포함되나요? | 해당 날짜의 첫 DANGER만 count를 1 증가시키고 같은 날 추가 DANGER는 증가시키지 않는다. 자동 주시 `+1초` CAUTION 행은 DANGER 누적 대상이 아니다. | 1 | Yes | Yes | Yes | 46 | 0.723766045986108 | The first chunk contains the first-DANGER-only rule, same-day behavior, and exclusion of the `+1초` CAUTION row. |

### Per-question results — Gwangmyeong AI/IoT PDF

| ID | Source document | Category | Exact query | Expected answer | First sufficient rank | Top-1 | Top-3 | Top-5 | Chunk ID | Cosine similarity | Evaluation note |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | ---: | ---: | --- |
| PDF-Q01 | `광명시 AI.pdf` | Broad semantic | 광명시 AI·IoT 기반 어르신 건강관리사업은 어떤 사업인가요? | 건강관리가 필요한 65세 이상 어르신에게 스마트 건강측정기기를 제공하고 ‘오늘건강’ 앱으로 광명시보건소가 관리하는 비대면 건강관리사업이다. | 1 | Yes | Yes | Yes | 54 | 0.842466261699416 | The first chunk contains the complete business definition. |
| PDF-Q02 | `광명시 AI.pdf` | Specific rule/process | 이 사업의 대상자는 누구이며 어떤 사람이 우선 고려되나요? | 광명시 거주 65세 이상 중 노쇠·만성질환 예방관리 또는 건강행태 개선이 필요한 사람이며, 통합돌봄 연계 대상자, 수급자·차상위계층, 관리되지 않는 만성질환자와 위험군 등이 우선 고려된다. | 2 | No | Yes | Yes | 54 | 0.456949300556864 | The first chunk starts mid-list and gives only part of the priority groups. Chunk 54 is the first result containing both the target population and the complete priority-group evidence. |
| PDF-Q03 | `광명시 AI.pdf` | Specific rule/process | 사업 신청 후 6개월 비대면 관리까지 어떤 순서로 진행되나요? | 신청·선별, 방문간호사 건강 스크리닝, 건강군·전허약군·허약군 등 분류, 필요한 디바이스와 월별 미션 제공, 6개월 비대면 관리 순서다. | 1 | Yes | Yes | Yes | 55 | 0.549922656372962 | The first chunk contains the complete five-stage sequence. Duplicate unrelated test rows appeared at ranks 3 and 4 but did not displace the sufficient rank-1 result. |
| PDF-Q04 | `광명시 AI.pdf` | Specific rule/process | 참여자에게 건강측정기기는 어떻게 제공되며 적극 참여 후에는 어떻게 되나요? | 건강 상태와 위험요인에 따라 스마트밴드·체중계·혈압계·혈당계 중 1인당 2종을 선별 대여하고, 6개월간 적극 참여한 대상자에게 대여기기를 증정한다. | 1 | Yes | Yes | Yes | 56 | 0.649975679157388 | The first chunk contains the selection, two-device loan, and six-month gift rules. |
| PDF-Q05 | `광명시 AI.pdf` | Numeric/year | 2024년 광명시 AI·IoT 어르신 건강관리사업 참여자 수는 몇 명으로 보고됐나요? | 920명이다. | 3 | No | Yes | Yes | 58 | 0.603210085552411 | Two semantically broad project/device chunks ranked above the operating-results chunk; chunk 58 is the first result containing the exact year and `920명`. |
| PDF-Q06 | `광명시 AI.pdf` | Numeric/year | 광명시는 서비스를 언제 시작했고 2022년 참여자는 몇 명이었나요? | 2021년 11월 15일 시작했고, 2022년 참여자는 187명이었다. | 1 | Yes | Yes | Yes | 54 | 0.506080424017203 | The first chunk contains both the exact start date and 2022 participant count. |
| PDF-Q07 | `광명시 AI.pdf` | Exact entity/name | 광명시에서 이 사업을 담당하는 부서와 주요 업무는 무엇인가요? | 광명시보건소 보건정책과 생명존중팀이 담당하며, 사업계획·예산, 참여자 모집·등록, 사업인력 및 대상자 관리를 수행한다. | 2 | No | Yes | Yes | 55 | 0.445445301941570 | The first chunk describes the project and target population but does not name the responsible team or duties. Chunk 55 contains the exact department/team and work list. |
| PDF-Q08 | `광명시 AI.pdf` | Boundary/threshold | 오늘건강 앱 미접속과 연락 불가가 어느 정도 지속되면 퇴록될 수 있나요? | 1개월 이상 앱에 접속하지 않고 연락도 되지 않을 경우 퇴록될 수 있다. | 1 | Yes | Yes | Yes | 57 | 0.582925537933841 | The first chunk contains the exact one-month and unreachable conditions. |
| PDF-Q09 | `광명시 AI.pdf` | Exact entity/name | ‘오늘건강’ 앱은 광명시가 자체 개발한 앱인가요? 누가 추진한 사업에서 사용하는 앱인가요? | 광명시 자체 개발 앱이 아니며, 보건복지부와 한국건강증진개발원이 추진하는 사업에서 전국 참여 보건소가 공통 사용하는 대상자용 앱이다. | 2 | No | Yes | Yes | 58 | 0.704185144467806 | The first chunk explains app usage but not its development/program ownership. Chunk 58 is the first to state that it is not city-developed and name both organizations. |
| PDF-Q10 | `광명시 AI.pdf` | Numeric/year | 2025년 참여자 수는 얼마로 보고됐고, 그 수치에는 어떤 해석상 주의점이 있나요? | 2025년 11월 27일 행정사무감사에서 1,198명으로 보고됐다. 정확한 집계 기준일과 연말 최종 실적 여부는 확인되지 않으며 누적 성격일 수 있다. | MISS | No | No | No | — | — | The first chunk contains the reporting/cutoff/finality/cumulative caveats but omits `1,198명`; the second contains `2025년 1,198명` but not the complete caveat. No single Top-5 chunk supports the complete answer. |

### Aggregate metrics

| Scope | Questions | Top-1 | Top-3 | Top-5 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| Overall | 20 | 12/20 (60%) | 17/20 (85%) | 18/20 (90%) | 0.7183 |
| Markdown document | 10 | 7/10 (70%) | 8/10 (80%) | 9/10 (90%) | 0.7533 |
| PDF document | 10 | 5/10 (50%) | 9/10 (90%) | 9/10 (90%) | 0.6833 |

MRR is the arithmetic mean of reciprocal first-sufficient-evidence ranks;
each `MISS` contributes 0.

### Category metrics

| Category | Questions | Top-1 | Top-3 | Top-5 |
| --- | ---: | ---: | ---: | ---: |
| Broad semantic | 2 | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |
| Specific rule/process | 7 | 5/7 (71.43%) | 6/7 (85.71%) | 6/7 (85.71%) |
| Boundary/threshold | 4 | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) |
| Exact entity/name | 4 | 0/4 (0%) | 3/4 (75%) | 4/4 (100%) |
| Numeric/year | 3 | 1/3 (33.33%) | 2/3 (66.67%) | 2/3 (66.67%) |
| **Total** | **20** | **12/20 (60%)** | **17/20 (85%)** | **18/20 (90%)** |

Category totals use the single primary category assigned in the fixed benchmark
definition; they sum to 20.

### Rank distribution

| Result | Count |
| --- | ---: |
| Rank 1 | 12 |
| Rank 2 | 3 |
| Rank 3 | 2 |
| Rank 4 | 0 |
| Rank 5 | 1 |
| MISS | 2 |
| **Total** | **20** |

Questions not at rank 1 were `MD-Q03`, `MD-Q05`, `MD-Q06`, `PDF-Q02`,
`PDF-Q05`, `PDF-Q07`, `PDF-Q09`, and `PDF-Q10`. The two misses were
`MD-Q05` and `PDF-Q10`.

### Observed ranking and failure patterns

Observed behavior:

- Broad semantic and boundary/threshold questions were all rank 1 in this run.
- Exact entity/name questions were all below rank 1: two were rank 2, one rank
  3, and one rank 5. Higher-ranked chunks were related to the requested subject
  but lacked the exact destination/conflict rule, selection query, responsible
  team, or app-program ownership needed by the ground truth.
- `PDF-Q05` showed a numeric/year precision issue: broad project and device
  chunks ranked ahead of the chunk containing the exact `2024년 920명` value.
- `MD-Q05` and `PDF-Q10` were misses because different returned chunks held
  complementary parts of the expected answer; no individual Top-5 chunk was
  sufficient under the fixed scoring rule.
- `PDF-Q02` returned a partial priority-list continuation before the chunk that
  contained both the target population and all required priority groups.
- Duplicate unrelated test rows occupied ranks 3 and 4 for `PDF-Q03`, although
  the sufficient source chunk still ranked first. Existing duplicate and test
  rows remain a possible influence on the available Top-5 result slots.

Possible explanations to investigate in later controlled comparisons:

- Semantic similarity may favor broad or adjacent topic coverage over exact
  entity, numeric, or fine-grained rule evidence for some queries.
- The two split-evidence misses may relate to where source material crosses
  chunk boundaries, but this baseline alone does not demonstrate that chunk
  size or overlap is the cause.
- Duplicate/test-row interference can consume result positions, but this run
  does not establish that duplicates changed any first-sufficient rank.

These are hypotheses for future A/B evaluation, not changes or conclusions
about the current retrieval design.

### Benchmark limitations

- Twenty questions remain a relatively small benchmark.
- Results apply only to these two project documents, these exact fixed
  questions, and the current database contents/configuration on 2026-08-20.
- Existing duplicate and synthetic test rows may influence ranking.
- This benchmark measures retrieval ranking, not answer-generation quality.
- Similarity values are cosine similarity scores, not confidence, probability,
  or accuracy.
- This baseline alone does not establish an optimal chunk size, overlap, model,
  or retrieval method.
- The earlier ten-question result remains a separate historical baseline; its
  Top-1 70%, Top-3 100%, and Top-5 100% values are not replaced by this run.
