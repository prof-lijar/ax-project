# Weekly-report native Slack table review

Date: 2026-09-29

Status: implemented after explicit backend authorization; native-block API and producer connected.

The Slack [Table block documentation](https://docs.slack.dev/reference/block-kit/blocks/table-block/) supports native rows, columns, alignment and wrapping. The backend now accepts validated native header, section, context, divider and table blocks, plus a generated-table convenience format.

## Proposed message (all information retained)

주간 리포트 저장 현황

지난주 누락 1명 · 전주 대비 1명 감소
가입자 6,601명 중 6,600명 저장 완료

지난주 (2026/09/21~09/27)
2주 전 (2026/09/14~09/20)

| 지역 | 주차 | 가입자(명) | 성공(명) | 실패·누락(명) | 누락률 | 전주 대비 누락률 |
| --- | --- | --- | --- | --- | --- | --- |
| 전체 | 지난주 | 6,601 | 6,600 | 1 | 0.02% | 0.02%p 감소 |
| 전체 | 2주 전 | 6,601 | 6,599 | 2 | 0.03% | 기준 주 |
| 울진 | 지난주 | 3,000 | 3,000 | 0 | 0.00% | 변동 없음 (0.00%p) |
| 울진 | 2주 전 | 3,000 | 3,000 | 0 | 0.00% | 기준 주 |
| 영덕 | 지난주 | 3,023 | 3,023 | 0 | 0.00% | 변동 없음 (0.00%p) |
| 영덕 | 2주 전 | 3,023 | 3,023 | 0 | 0.00% | 기준 주 |
| 광명 | 지난주 | 451 | 450 | 1 | 0.22% | 0.22%p 감소 |
| 광명 | 2주 전 | 451 | 449 | 2 | 0.44% | 기준 주 |
| 기타 | 지난주 | 127 | 127 | 0 | 0.00% | 변동 없음 (0.00%p) |
| 기타 | 2주 전 | 127 | 127 | 0 | 0.00% | 기준 주 |

집계 기준
• 성공: 운영 DB에 해당 주 리포트가 있음 · 실패(누락): 리포트가 없음
• 누락률 = 실패 ÷ 가입자 수 × 100 · 가입자 0명은 산정·비교 불가
• 전주 대비 = 지난주 누락률 − 2주 전 누락률 · 감소할수록 개선
• %p는 퍼센트포인트(두 비율의 차이) · 원자료로 계산 후 소수 둘째 자리 반올림
• 두 주 모두 조회 시점의 동일한 가입자·주소 기준 · 미분류 주소는 기타
• 과거 가입·탈퇴 및 주소 변경 이력 미반영 · 기존 저장 리포트도 성공에 포함

## Implementation and verification

- Added validated native blocks, plus optional generated table/footer and Korean locale.
- Render exactly one native table with seven columns and ten data rows, aligned numeric columns and wrapping. Keep the complete screen-reader fallback.
- Preserve old notification fingerprints by omitting unset new fields during normalization; pending messages keep their frozen original body.
- Supported native blocks are schema-validated; no database migration, credential or destination changes.
- Nine isolated tests passed: actual native rendering, every production aggregate retained, empty and increasing rates, rectangular/table-size limits, literal mentions and legacy idempotency.
- Native-table delivery was confirmed in the approved test channel. Backend API authentication and deployment limitations still apply.

The reviewed patch has been applied and superseded by the complete native-block
implementation. See [backend API and rollout](../../docs/08-implementation/slack-notification-native-blocks.md).

Final native-block validation: backend 243 passed / 5 skipped; agents 713 passed /
25 skipped. A native-block test message was delivered through the backend sender
to `#nexgent-test` (timestamp `1790670192.238509`). No service was deployed.
