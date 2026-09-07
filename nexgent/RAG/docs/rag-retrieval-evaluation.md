# RAG Retrieval Evaluation

This document owns the fixed retrieval benchmark, dated vector baselines, and
the experimental lexical/RRF comparison. It does not describe production API
operation; see [RAG Server](rag-server.md) and
[Vector Search](rag-vector-search.md).

Production retrieval remains Qwen query embedding plus exact pgvector cosine
ranking. Lexical ranking and RRF are experimental only.

## Evaluation rule

- The 20 question strings and expected answers below are immutable comparison
  inputs drawn from two real project documents.
- Rank is the first returned chunk that **alone** contains sufficient evidence
  for the complete expected answer. Evidence is not combined across chunks.
- `MISS` means no sufficient single chunk appeared in Top-5 and contributes 0
  to MRR.
- Similarity is a cosine ranking score, not probability, confidence, or answer
  accuracy.
- Retrieval evaluation does not measure answer generation.

## Fixed questions — Recovery data-lineage Markdown

| ID | Category | Question | Expected answer | Ground-truth evidence / reference |
| --- | --- | --- | --- | --- |
| MD-Q01 | Broad semantic | 과거 ward evaluation을 복구할 때 구현의 최종 source of truth는 무엇인가요? | `analysis_wardevaluation_recovery_data_lineage.md`에 정의된 Recovery 정책이 최종 source of truth이며, 기존 Production 문서는 참고 자료다. | “이 문서의 Recovery 정책이 구현의 최종 source of truth다.” — §1 문서 목적 |
| MD-Q02 | Specific rule/process | 동일 ward의 최신 daily timestamp에 여러 IMEI 문서가 있으면 last_vital_sign_timestamp를 어떻게 선택하나요? | 최신 timestamp의 모든 IMEI 후보에서 null이 아닌 vital 시각을 정규화한 뒤 가장 최신 값을 선택하며, 모두 null이면 `None`을 사용한다. | “그중 가장 최신 값을 … 선택한다”, “모든 후보가 null이면 `None`” — §10 |
| MD-Q03 | Exact entity/name | Recovery 결과의 유일한 저장 대상과 재실행 시 충돌 처리 기준은 무엇인가요? | 유일한 destination은 `archive.analysis_wardevaluation`이며, `(ward_id, evaluated_at)` 충돌 시 `DO NOTHING`으로 기존 행을 바꾸지 않는다. | “Destination은 `archive.analysis_wardevaluation` 하나”, unique key와 `DO NOTHING` — §6, §18 |
| MD-Q04 | Boundary/threshold | Recovery evaluated_at 시계열은 시작·종료 시각과 5분 경계를 어떻게 처리하나요? | start와 end를 포함하고 5분씩 증가시키되 초·마이크로초만 0으로 정규화한다. 시작 분을 5의 배수로 floor하지 않아 시작이 `:03`이면 `:03, :08, :13...`이다. | `start <= evaluated_at <= end`, “시작 분… 별도 floor하지 않는다” — §8 |
| MD-Q05 | Specific rule/process | 자동 주시 전환의 조건과 생성되는 두 행은 무엇인가요? | MORNING 정상 계산이 `DANGER`, 누적 전 `danger_counts >= 7`, 마지막 DANGER 날짜가 현재 KST 날짜보다 이전일 때 전환한다. 원래 DANGER 행과 `+1초`의 모든 점수 70인 CAUTION 행을 만든다. | 조건 3개와 “원래 `DANGER` row”, “`evaluated_at + 1초`” — §15 |
| MD-Q06 | Exact entity/name | Recovery 평가 대상 ward_id는 어느 source와 query 의미로 선정하나요? | `archive.resources_measurement`에서 null이 아닌 distinct `ward_id`를 정렬해 선정하며, `ansimk.resources_location`이나 현재 설치 상태는 사용하지 않는다. | `SELECT DISTINCT ward_id ... WHERE ward_id IS NOT NULL` — §7 |
| MD-Q07 | Boundary/threshold | score 25, 26, 50, 51, 75, 76은 각각 어떤 risk level인가요? | 25 DANGER, 26 ALERT, 50 ALERT, 51 CAUTION, 75 CAUTION, 76 STABLE이다. | 경계 검증값 목록 — §12 Risk level |
| MD-Q08 | Boundary/threshold | `is_out=True`일 때 마지막 반응 후 정확히 30분인 경우와 30분을 초과한 경우의 처리가 어떻게 다른가요? | 30분 초과면 모든 점수 70과 `user_is_out=True`를 반환한다. 정확히 30분 이내면 메모리 `is_out=False`로 바꾸고 일반 계산으로 진행한다. | “30분을 초과하면…70”, “정확히 30분 이내이면…일반 계산” — §14 |
| MD-Q09 | Specific rule/process | 조회 범위에 device-daily 문서가 하나도 없으면 점수와 상태값은 어떻게 설정되나요? | overall과 다섯 component 점수를 모두 30으로 설정하고 `device_has_signal=False`, `user_is_out=False`로 둔다. | “모든 점수를 30”, 두 boolean 값 — §11 |
| MD-Q10 | Specific rule/process | 같은 KST 날짜에 DANGER가 여러 번 발생하면 danger_counts는 어떻게 누적되며 자동 주시 +1초 행은 포함되나요? | 해당 날짜의 첫 DANGER만 count를 1 증가시키고 같은 날 추가 DANGER는 증가시키지 않는다. 자동 주시 `+1초` CAUTION 행은 DANGER 누적 대상이 아니다. | “첫 DANGER일 때만”, “같은 날짜의 추가 DANGER는…않는다” — §16 |

## Fixed questions — Gwangmyeong AI/IoT PDF

| ID | Category | Question | Expected answer | Ground-truth evidence / reference |
| --- | --- | --- | --- | --- |
| PDF-Q01 | Broad semantic | 광명시 AI·IoT 기반 어르신 건강관리사업은 어떤 사업인가요? | 건강관리가 필요한 65세 이상 어르신에게 스마트 건강측정기기를 제공하고 ‘오늘건강’ 앱으로 광명시보건소가 관리하는 비대면 건강관리사업이다. | 사업 정의 — §1 사업 개요 |
| PDF-Q02 | Specific rule/process | 이 사업의 대상자는 누구이며 어떤 사람이 우선 고려되나요? | 광명시 거주 65세 이상 중 노쇠·만성질환 예방관리 또는 건강행태 개선이 필요한 사람이며, 통합돌봄 연계 대상자, 수급자·차상위계층, 관리되지 않는 만성질환자와 위험군 등이 우선 고려된다. | 대상과 우선 고려 대상 — §2 |
| PDF-Q03 | Specific rule/process | 사업 신청 후 6개월 비대면 관리까지 어떤 순서로 진행되나요? | 신청·선별, 방문간호사 건강 스크리닝, 건강군·전허약군·허약군 등 분류, 필요한 디바이스와 월별 미션 제공, 6개월 비대면 관리 순서다. | 운영 절차 도식 — §3 운영 방식 |
| PDF-Q04 | Specific rule/process | 참여자에게 건강측정기기는 어떻게 제공되며 적극 참여 후에는 어떻게 되나요? | 건강 상태와 위험요인에 따라 스마트밴드·체중계·혈압계·혈당계 중 1인당 2종을 선별 대여하고, 6개월간 적극 참여한 대상자에게 대여기기를 증정한다. | “1인당 2종”, “6개월간…증정” — §4 |
| PDF-Q05 | Numeric/year | 2024년 광명시 AI·IoT 어르신 건강관리사업 참여자 수는 몇 명으로 보고됐나요? | 920명이다. | “2024년 920명” — §6 사업 운영실적 |
| PDF-Q06 | Numeric/year | 광명시는 서비스를 언제 시작했고 2022년 참여자는 몇 명이었나요? | 2021년 11월 15일 시작했고, 2022년 참여자는 187명이었다. | 시작일과 2022년 수치 — §1, §6 |
| PDF-Q07 | Exact entity/name | 광명시에서 이 사업을 담당하는 부서와 주요 업무는 무엇인가요? | 광명시보건소 보건정책과 생명존중팀이 담당하며, 사업계획·예산, 참여자 모집·등록, 사업인력 및 대상자 관리를 수행한다. | 담당 부서와 업무 — §2 |
| PDF-Q08 | Boundary/threshold | 오늘건강 앱 미접속과 연락 불가가 어느 정도 지속되면 퇴록될 수 있나요? | 1개월 이상 앱에 접속하지 않고 연락도 되지 않을 경우 퇴록될 수 있다. | “1개월 이상…접속하지 않고 연락도 되지 않을 경우” — §5 |
| PDF-Q09 | Exact entity/name | ‘오늘건강’ 앱은 광명시가 자체 개발한 앱인가요? 누가 추진한 사업에서 사용하는 앱인가요? | 광명시 자체 개발 앱이 아니며, 보건복지부와 한국건강증진개발원이 추진하는 사업에서 전국 참여 보건소가 공통 사용하는 대상자용 앱이다. | 앱의 개발·운영 주체 설명 — §5 |
| PDF-Q10 | Numeric/year | 2025년 참여자 수는 얼마로 보고됐고, 그 수치에는 어떤 해석상 주의점이 있나요? | 2025년 11월 27일 행정사무감사에서 1,198명으로 보고됐다. 정확한 집계 기준일과 연말 최종 실적 여부는 확인되지 않으며 누적 성격일 수 있다. | 2025년 `1,198명`과 주의 문구 — §6 |

## Categories

| Category | IDs | Count |
| --- | --- | ---: |
| Broad semantic | MD-Q01, PDF-Q01 | 2 |
| Specific rule/process | MD-Q02, MD-Q05, MD-Q09, MD-Q10, PDF-Q02, PDF-Q03, PDF-Q04 | 7 |
| Boundary/threshold | MD-Q04, MD-Q07, MD-Q08, PDF-Q08 | 4 |
| Exact entity/name | MD-Q03, MD-Q06, PDF-Q07, PDF-Q09 | 4 |
| Numeric/year | PDF-Q05, PDF-Q06, PDF-Q10 | 3 |
| **Total** |  | **20** |

An earlier 10-question manual sample measured Top-1 7/10, Top-3 10/10, and
Top-5 10/10. It is historical context only; the fixed set above is the
authoritative benchmark definition.

## Historical vector baseline — 2026-08-20

All 20 questions were submitted unchanged with `top_k=5`. Retrieval used
`Qwen/Qwen3-Embedding-0.6B`, `prompt_name="query"`, normalized 1024-dimensional
vectors, and exact pgvector cosine search. Neither source was re-ingested.

| ID | First sufficient rank | Row ID | Cosine similarity |
| --- | ---: | ---: | ---: |
| MD-Q01 | 1 | 33 | 0.691837120040582 |
| MD-Q02 | 1 | 39 | 0.829801932119689 |
| MD-Q03 | 5 | 48 | 0.570755361975513 |
| MD-Q04 | 1 | 38 | 0.697981127440638 |
| MD-Q05 | MISS | — | — |
| MD-Q06 | 3 | 37 | 0.651470632434433 |
| MD-Q07 | 1 | 43 | 0.577695185621574 |
| MD-Q08 | 1 | 45 | 0.523497514843804 |
| MD-Q09 | 1 | 43 | 0.641615369223309 |
| MD-Q10 | 1 | 46 | 0.723766045986108 |
| PDF-Q01 | 1 | 54 | 0.842466261699416 |
| PDF-Q02 | 2 | 54 | 0.456949300556864 |
| PDF-Q03 | 1 | 55 | 0.549922656372962 |
| PDF-Q04 | 1 | 56 | 0.649975679157388 |
| PDF-Q05 | 3 | 58 | 0.603210085552411 |
| PDF-Q06 | 1 | 54 | 0.506080424017203 |
| PDF-Q07 | 2 | 55 | 0.445445301941570 |
| PDF-Q08 | 1 | 57 | 0.582925537933841 |
| PDF-Q09 | 2 | 58 | 0.704185144467806 |
| PDF-Q10 | MISS | — | — |

| Scope | Top-1 | Top-3 | Top-5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Overall | 12/20 (60%) | 17/20 (85%) | 18/20 (90%) | 0.7183 |
| Recovery Markdown | 7/10 (70%) | 8/10 (80%) | 9/10 (90%) | 0.7533 |
| Gwangmyeong PDF | 5/10 (50%) | 9/10 (90%) | 9/10 (90%) | 0.6833 |

| Category | Top-1 | Top-3 | Top-5 |
| --- | ---: | ---: | ---: |
| Broad semantic | 2/2 | 2/2 | 2/2 |
| Specific rule/process | 5/7 | 6/7 | 6/7 |
| Boundary/threshold | 4/4 | 4/4 | 4/4 |
| Exact entity/name | 0/4 | 3/4 | 4/4 |
| Numeric/year | 1/3 | 2/3 | 2/3 |

The misses were `MD-Q05` and `PDF-Q10`, where complete expected evidence was
split across chunks. Exact entity and numeric questions were weaker than broad
semantic and boundary questions. Duplicate/synthetic rows existed in the
corpus and could occupy result slots.

## Larger-corpus vector regression — 2026-08-24

The same 20 strings and scoring rule were used once each with `top_k=5` against
a 109-embedding corpus containing the original legacy chunks plus later OCR,
PDF, DOCX, Direct Text, duplicate, and synthetic/test content. No benchmark
source was re-ingested.

| ID | Top-5 row IDs in server order | Rank | Sufficient row | Cosine similarity | Change from baseline |
| --- | --- | ---: | ---: | ---: | --- |
| MD-Q01 | 33, 51, 37, 50, 35 | 1 | 33 | 0.6918371200405818 | Unchanged |
| MD-Q02 | 39, 36, 51, 53, 38 | 1 | 39 | 0.8298019321196889 | Unchanged |
| MD-Q03 | 50, 53, 49, 34, 48 | 5 | 48 | 0.5707553619755128 | Unchanged |
| MD-Q04 | 38, 33, 50, 48, 51 | 1 | 38 | 0.6979811274406384 | Unchanged |
| MD-Q05 | 45, 46, 48, 52, 50 | MISS | — | — | Unchanged |
| MD-Q06 | 33, 50, 37, 51, 44 | 3 | 37 | 0.651470632434433 | Unchanged |
| MD-Q07 | 43, 42, 40, 37, 41 | 1 | 43 | 0.577695185621574 | Unchanged |
| MD-Q08 | 45, 41, 47, 46, 44 | 1 | 45 | 0.5251230829683815 | Unchanged |
| MD-Q09 | 43, 36, 53, 39, 38 | 1 | 43 | 0.641615369223309 | Unchanged |
| MD-Q10 | 46, 47, 45, 44, 43 | 1 | 46 | 0.7237660459861083 | Unchanged |
| PDF-Q01 | 54, 95, 57, 103, 96 | 1 | 54 | 0.8424662616994163 | Unchanged |
| PDF-Q02 | 55, 54, 93, 89, 96 | 2 | 54 | 0.4569493005568638 | Unchanged |
| PDF-Q03 | 55, 102, 93, 95, 98 | 1 | 55 | 0.5499226563729619 | Unchanged |
| PDF-Q04 | 56, 57, 58, 55, 54 | 1 | 56 | 0.6499756791573883 | Unchanged |
| PDF-Q05 | 54, 95, 57, 58, 103 | 4 | 58 | 0.603210085552411 | Worsened from 3 |
| PDF-Q06 | 54, 55, 93, 57, 58 | 1 | 54 | 0.5060804240172034 | Unchanged |
| PDF-Q07 | 54, 55, 105, 104, 57 | 2 | 55 | 0.44544530194157006 | Unchanged |
| PDF-Q08 | 57, 58, 56, 55, 75 | 1 | 57 | 0.582925537933841 | Unchanged |
| PDF-Q09 | 57, 58, 56, 54, 55 | 2 | 58 | 0.7041851444678063 | Unchanged |
| PDF-Q10 | 59, 93, 58, 96, 70 | MISS | — | — | Unchanged |

| Run | Top-1 | Top-3 | Top-5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Historical baseline | 12/20 (60%) | 17/20 (85%) | 18/20 (90%) | 0.7183 |
| Larger-corpus regression | 12/20 (60%) | 16/20 (80%) | 18/20 (90%) | 0.7142 |

Only `PDF-Q05` changed, from rank 3 to rank 4. A later DOCX chunk entered rank
2 and shifted the sufficient legacy row. No MISS became a hit, no hit became a
MISS, and Top-1/Top-5 were unchanged. The evidence supports corpus competition,
not a change in Qwen configuration, chunking, cosine SQL, or response ordering.

The regression category metrics were:

| Category | Top-1 | Top-3 | Top-5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Broad semantic | 2/2 | 2/2 | 2/2 | 1.0000 |
| Specific rule/process | 5/7 | 6/7 | 6/7 | 0.7857 |
| Boundary/threshold | 4/4 | 4/4 | 4/4 | 1.0000 |
| Exact entity/name | 0/4 | 3/4 | 4/4 | 0.3833 |
| Numeric/year | 1/3 | 1/3 | 2/3 | 0.4167 |

## Experimental lexical and RRF evaluation — 2026-08-24

This read-only experiment used the same 109-row corpus, fixed questions, and
single-sufficient-chunk rule. It did not change production search.

### Methods

- **Vector-only:** unchanged Qwen exact cosine retrieval, Top-20 candidates.
- **Lexical-only:** experimental Python corpus scan with Unicode NFC,
  case/whitespace normalization, exact substring/token occurrence,
  corpus-frequency weighting, and additional weight for numeric and ASCII
  technical tokens. It is not BM25.
- **RRF hybrid:** vector Top-20 plus lexical Top-20 using
  `1/(60 + vector_rank) + 1/(60 + lexical_rank)`.

### Results

| Method | Top-1 | Top-3 | Top-5 | MRR |
| --- | ---: | ---: | ---: | ---: |
| Vector-only | 12/20 (60%) | 16/20 (80%) | 18/20 (90%) | 0.7142 |
| Lexical-only | 15/20 (75%) | 16/20 (80%) | 16/20 (80%) | 0.7667 |
| RRF hybrid | 13/20 (65%) | 17/20 (85%) | 18/20 (90%) | 0.7458 |

| ID | Vector | Lexical | RRF hybrid | Hybrid change |
| --- | ---: | ---: | ---: | --- |
| MD-Q01 | 1 | 1 | 1 | Unchanged |
| MD-Q02 | 1 | 1 | 1 | Unchanged |
| MD-Q03 | 5 | 3 | 3 | Improved |
| MD-Q04 | 1 | 1 | 1 | Unchanged |
| MD-Q05 | MISS | MISS | MISS | Unchanged |
| MD-Q06 | 3 | 1 | 1 | Improved |
| MD-Q07 | 1 | 1 | 1 | Unchanged |
| MD-Q08 | 1 | 1 | 1 | Unchanged |
| MD-Q09 | 1 | MISS | 3 | Worsened |
| MD-Q10 | 1 | 1 | 1 | Unchanged |
| PDF-Q01 | 1 | 1 | 1 | Unchanged |
| PDF-Q02 | 2 | 1 | 1 | Improved |
| PDF-Q03 | 1 | 1 | 1 | Unchanged |
| PDF-Q04 | 1 | 1 | 1 | Unchanged |
| PDF-Q05 | 4 | 1 | 2 | Improved |
| PDF-Q06 | 1 | 1 | 1 | Unchanged |
| PDF-Q07 | 2 | MISS | 4 | Worsened |
| PDF-Q08 | 1 | 1 | 1 | Unchanged |
| PDF-Q09 | 2 | 1 | 2 | Unchanged |
| PDF-Q10 | MISS | MISS | MISS | Unchanged |

| Category | Vector MRR | Lexical MRR | RRF MRR |
| --- | ---: | ---: | ---: |
| Broad semantic | 1.0000 | 1.0000 | 1.0000 |
| Specific rule/process | 0.7857 | 0.7143 | 0.7619 |
| Boundary/threshold | 1.0000 | 1.0000 | 1.0000 |
| Exact entity/name | 0.3833 | 0.5833 | 0.5208 |
| Numeric/year | 0.4167 | 0.6667 | 0.5000 |

RRF improved `MD-Q03`, `MD-Q06`, `PDF-Q02`, and `PDF-Q05`; worsened
`MD-Q09` and `PDF-Q07`; and left 14 questions unchanged. No MISS became a hit
and no hit became a MISS. Broad-semantic and boundary performance was
preserved; lexical evidence helped exact-name and numeric queries but did not
materially improve the specific-rule category.

Later documents competed for Top-5 slots. RRF lists contained ten appearances
from the later DOCX, four from `SK텔레콤2222.pdf`, and one from
`ocr_test_doc.pdf`. `PDF-Q07` worsened partly because SK Telecom chunks took
high lexical positions; `PDF-Q05` improved despite DOCX competition. Corpus
competition was real but not uniformly positive or negative.

### Decision

Keep production vector-only. RRF produced a measurable but small aggregate gain
on only 20 questions, worsened two questions, and depended on an unindexed
Python corpus scan. Before production consideration, expand the benchmark and
corpus, evaluate Korean-suitable indexed lexical retrieval, test candidate
depths and RRF parameters, and investigate `MD-Q09` and `PDF-Q07`. No
Elasticsearch, OpenSearch, or BM25 architecture has been selected.

## Corpus-state and benchmark limitations

These results are dated evidence for corpus states that existed before the live
Empty Database validation. That operation removed the 109-row evaluation
corpus; a later synthetic RAG Chat document was ingested for a separate
functional validation. Deletion does not invalidate or recompute the recorded
questions, ranks, row IDs, similarities, or metrics.

The pre-empty backups were structurally inspected but have not been restored.
Post-restore counts, identity/sequence fidelity, retrieval regression, and
benchmark equivalence remain unvalidated.

The benchmark is too small to establish production accuracy or an optimal
model, chunk size, overlap, or retrieval method. Future runs must preserve the
fixed 20 questions and add new dated results rather than overwriting either
vector baseline.
