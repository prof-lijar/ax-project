# `archive.analysis_wardevaluation` Recovery Data Lineage

## 1. 문서 목적

이 문서는 과거 ward evaluation을 재계산하여 `archive.analysis_wardevaluation`에 복구하기 위한 별도의 data lineage와 구현 기준을 정의한다. 기존 `analysis_wardevaluation_data_lineage.md`는 Production 동작을 설명하는 참고 자료이고, 이 문서의 Recovery 정책이 구현의 최종 source of truth다.

Recovery는 다음 흐름만 사용한다.

```text
PostgreSQL archive.resources_measurement
  -> MongoDB safeguard-staging["device-daily"]
  + ansimk.analysis_wardevaluation의 시작 이전 DANGER 이력(SELECT only)
  + Asia/Seoul evaluated_at 시계열
  + Python 메모리 ward state
  -> 시간대별 risk score와 note 재계산
  -> PostgreSQL archive.analysis_wardevaluation
```

## 2. 복구 범위

### 읽기 source

- PostgreSQL raw source: `archive.resources_measurement`
- MongoDB intermediate source: database `safeguard-staging`, collection `device-daily`
- 초기 DANGER state 참고: `ansimk.analysis_wardevaluation`, `start_datetime` 이전 행에 대한 SELECT only

### 유일한 향후 쓰기 destination

- `archive.analysis_wardevaluation`

현재 `ansimk.resources_ward` snapshot은 과거 state의 source로 사용하지 않는다. 현재 설치 관계로 과거 센서 소유 관계를 다시 계산하지 않으며, Kafka, notifier, `analyze_write_db`, Production trigger를 실행하지 않는다.

Production 근거: Production은 MongoDB `device_daily`와 현재 `resources_ward`를 함께 읽지만(`analyze_utils.py:analyze_user_stats()`), Recovery는 이 부분을 확정 정책으로 대체한다.

## 3. Production과 Recovery 비교

| Production | Recovery |
|---|---|
| `resources_location`에서 ward 선택 | `archive.resources_measurement`의 distinct non-null `ward_id` 사용 |
| MongoDB `device_daily` 사용 | MongoDB `safeguard-staging["device-daily"]` 사용 |
| 현재 `resources_ward` state 사용 | 시작 이전 DANGER 이력과 메모리 ward state 사용 |
| `resources_ward` UPDATE | 메모리 state만 변경 |
| Kafka 기반 producer/consumer pipeline | 단일 chronological replay pipeline |
| `analyze_write_db` consumer 경유 | `archive.analysis_wardevaluation`에 직접 저장 |
| DB trigger based state updates | Recovery policy implemented in Python memory state |
| `ansimk.analysis_wardevaluation` 저장 | `archive.analysis_wardevaluation` 저장 |
| 최신 daily 문서 한 건을 `find_one()` | latest daily timestamp의 모든 IMEI 후보에서 최신 non-null vital 선택 |

Collection 이름은 중요한 schema 경계다. Production의 `db["device_daily"]`는 원래 동작을 설명하는 근거일 뿐이다. Recovery는 항상 다음 형태를 사용한다.

```python
database["device-daily"]
```

Recovery source로 `device_daily`를 조회하거나 새로 생성하지 않는다.

## 4. 전체 Data Lineage

```text
archive.resources_measurement
  fields: ward_id, imei, read_at,
          remote_control_count, movement_count,
          illumination, humidity, temperature
  historical ownership: ward_id + imei 그대로 사용
        |
        v
safeguard-staging.device-daily
  identity: imei + userid + Seoul daily timestamp
  evaluation input: userid, timestamp, last_vital_sign_timestamp
        |
        +---------------------------+
        |                           |
        v                           v
ward_id별 evaluated_at          ansimk.analysis_wardevaluation
KST 5분 시계열                start_datetime 이전 DANGER SELECT
        |                           |
        +-------------+-------------+
                      v
              Python memory ward state
              + Production-equivalent scoring
                      |
                      v
             archive.analysis_wardevaluation
```

`archive.resources_measurement.ward_id`와 `.imei`가 과거 관계의 source of truth다. `ansimk.resources_location`, 현재 device installation table, 현재 ward-device mapping을 사용해 이를 다시 매핑하지 않는다.

Production 근거: Production raw-to-ward 관계는 설치 정보를 통해 해석하지만, Recovery daily rebuild는 `rebuild_device_daily.py:load_groups()`에서 archived `ward_id`와 `imei`를 직접 사용한다.

## 5. 입력 데이터

### `archive.resources_measurement`

| 컬럼 | Recovery 용도 |
|---|---|
| `ward_id` | 평가 대상 선정 및 MongoDB `userid`의 원천 |
| `imei` | 과거 device identity와 daily document identity |
| `read_at` | KST 일자 구분 및 activity timestamp |
| `remote_control_count` | `> 0`이면 IR activity |
| `movement_count` | `> 0`이면 PIR activity |
| `illumination` | complete daily 통계용; ward risk 공식은 직접 읽지 않음 |
| `humidity` | complete daily 통계용; ward risk 공식은 직접 읽지 않음 |
| `temperature` | complete daily 통계용; ward risk 공식은 직접 읽지 않음 |

### `safeguard-staging.device-daily`

평가에 직접 필요한 필드는 다음과 같다.

- `userid`
- `imei`
- `timestamp`
- `last_vital_sign_timestamp`

`last_ir_timestamp`, `last_pir_timestamp`는 `last_vital_sign_timestamp` 생성·carry-forward의 근거지만 evaluation 계산에서 직접 읽을 필요는 없다. 통계 필드와 `updated_at`도 현재 ward risk 공식의 직접 입력이 아니다.

### `ansimk.analysis_wardevaluation`

각 대상 ward에 대해 `evaluated_at < start_datetime`인 기존 `DANGER` 행만 초기 danger state 계산에 사용한다. 날짜 구분은 `evaluated_at`을 `Asia/Seoul`로 해석한 calendar date를 기준으로 한다. 이 테이블은 수정하지 않는다.

Production 근거: `analyze_utils.py:analyze_user_stats()`는 daily 문서에서 `last_vital_sign_timestamp`를 읽고, `lib.analysis.upsert_wardevalutions()`가 evaluation을 저장한다.

## 6. 출력 데이터

Destination은 `archive.analysis_wardevaluation` 하나다.

| 컬럼 | 생성 규칙 |
|---|---|
| `id` | destination DB가 생성하며 Recovery INSERT에서 직접 공급하지 않음 |
| `evaluated_at` | KST timezone-aware 평가 시각 또는 자동 주시 시각 `+1초` |
| `risk_level` | overall `score`를 risk level로 변환 |
| `note` | Production note 규칙으로 생성 |
| `ward_id` | 대상 archived `ward_id` |
| `risk_score` | `int(score)` |
| `brightness_risk_level` | `light` score의 risk level |
| `humidity_risk_level` | `humidity` score의 risk level |
| `movement_risk_level` | `pirCount` score의 risk level |
| `remote_control_risk_level` | `irCount` score의 risk level |
| `temperature_risk_level` | `temperature` score의 risk level |

Unique key는 `(ward_id, evaluated_at)`이다. 재실행 안전성을 위해 INSERT는 이 key 충돌 시 기존 행을 변경하지 않는 `DO NOTHING` 방식으로 수행한다. 메모리 ward state와 자동 주시 flag는 destination 컬럼이 아니다.

Production 근거: `iot-server/analyze_user_stats.py:consumer_thread_impl()`의 tuple mapping, `iot-server/lib/analysis.py:upsert_wardevalutions()`의 10개 INSERT 컬럼과 `ON CONFLICT ... DO NOTHING`.

## 7. 평가 대상 ward_id

Recovery 대상은 다음 query 의미로 고정한다.

```sql
SELECT DISTINCT ward_id
FROM archive.resources_measurement
WHERE ward_id IS NOT NULL
ORDER BY ward_id;
```

`ansimk.resources_location`과 현재 설치 상태는 대상 선정에 사용하지 않는다. 따라서 Production에서는 평가했지만 선택한 archive 범위에 measurement가 전혀 없는 ward의 신호 없음 evaluation은 Recovery 결과에서 빠질 수 있다.

Production 근거: Production은 `analyze_utils.py:get_all_installed_ward_ids()`가 `resources_location.ward_id`를 distinct 조회한다. 위 query는 이를 대체하는 RECOVERY DIFFERENCE다.

## 8. evaluated_at 생성

평가 시각은 다음 규칙으로 생성한다.

- `start_datetime`과 `end_datetime`을 timezone-aware datetime으로 받는다.
- 계산 timezone은 `Asia/Seoul`이다.
- 오래된 시각부터 최신 시각 순서로 처리한다.
- 간격은 정확히 5분이다.
- 구현 명세상 양 끝을 포함한다: `start <= evaluated_at <= end`.
- 시계열은 정규화된 start에서 `timedelta(minutes=5)`를 반복해서 더한다.
- Production과 같이 초와 마이크로초는 0으로 정규화한다.
- 시작 분을 0, 5, 10 등의 wall-clock 5분 경계로 별도 floor하지 않는다. 예를 들어 시작 분이 03이면 `:03, :08, :13 ...` 순서다.
- end가 해당 시계열 격자에 정확히 놓이지 않으면 end보다 작거나 같은 마지막 시각까지만 생성한다.

Production 근거: `analyzer_user_stats_producer.py:user_stats_worker()`는 `start.replace(second=0, microsecond=0)` 후 `DELTA = timedelta(minutes=5)`를 반복하며, 분을 5의 배수로 정렬하지 않는다.

## 9. MongoDB device-daily 조회

각 `(ward_id, evaluated_at)`에 대해 `safeguard-staging["device-daily"]`만 다음 조건으로 조회한다.

```text
userid == ward_id
timestamp >= KST 평가일 자정 - 1일
timestamp <= evaluated_at
```

절차는 다음과 같다.

1. 범위에 포함되는 문서 중 가장 최신 `timestamp`를 구한다.
2. 그 latest timestamp와 동일한 모든 문서를 유지한다.
3. 더 오래된 daily timestamp 문서는 후보에서 제외한다.
4. 후보가 하나도 없으면 신호 없음 분기로 간다.

MongoDB datetime은 비교 전에 timezone-aware UTC/KST로 일관되게 정규화한다. Collection 선택은 반드시 `database["device-daily"]` 형태여야 한다.

Production 근거: `analyze_utils.py:analyze_user_stats()`의 전날 KST 자정 이상, evaluated_at 이하, timestamp 내림차순 `find_one()` 조건. 모든 latest-timestamp 후보를 유지하는 것은 RECOVERY DIFFERENCE다.

## 10. last_vital_sign_timestamp 선택

동일 ward의 latest daily timestamp에 여러 IMEI 문서가 있으면 deterministic하게 다음 규칙을 적용한다.

1. 모든 IMEI 후보의 `last_vital_sign_timestamp`를 확인한다.
2. null이 아닌 값을 timezone-aware datetime으로 정규화한다.
3. 그중 가장 최신 값을 ward evaluation의 `last_vital_sign_timestamp`로 선택한다.
4. 모든 후보가 null이면 `None`을 사용한다.

IMEI의 현재 설치 관계나 정렬 순서로 후보를 제거하지 않는다. 선택한 IMEI와 후보 수는 검증 로그에 남길 수 있지만 ward state에는 저장하지 않는다.

Production은 최신 daily 문서 한 건만 `find_one()`으로 선택하고 동일 timestamp tie-breaker가 없다. 위 규칙은 이를 대체하는 RECOVERY DIFFERENCE이며, 실행 순서와 MongoDB 반환 순서에 독립적인 결과를 보장한다.

Production 근거: `analyze_utils.py:analyze_user_stats()`의 단일 document lookup; Recovery daily identity 근거: `rebuild_device_daily.py:ensure_target_index()`와 `build_document()`.

## 11. 시간대별 risk_score

모든 비교는 `Asia/Seoul` 기준이다.

| 시간대 | 범위 |
|---|---|
| `AFTER_MIDNIGHT` | `00:00 <= T < 03:00` |
| `MORNING` | `03:00 <= T < 10:00` |
| `DAYTIME` | `10:00 <= T < 17:00` |
| `EVENING` | `17:00 <= T < 20:00` |
| `BEFORE_MIDNIGHT` | `20:00 <= T < 24:00` |

일반 계산의 초기값은 다음과 같다.

```text
score = 100
temperature = 100
humidity = 100
light = 100
irCount = 100
pirCount = 100
device_has_signal = True
user_is_out = False
```

`T`는 evaluated_at, `L`은 선택된 last vital KST 시각이다. 선형식의 경과분은 마지막 반응 자체가 아니라 해당 시간대 시작 시각부터 계산되는 경우가 많다.

| 평가 시간 | L 비교 | score 공식 |
|---|---|---:|
| 00:00–02:59 | 모든 경우 | 100; 감점 없음 |
| 03:00–09:59 | `L > 03:00` | 100 |
| 03:00–09:59 | `L <= 03:00` 또는 None | `int(100 - 100 * minutes_since_03 / 420)` |
| 10:00–16:59 | `L > 10:00` | 100 |
| 10:00–16:59 | `03:00 < L <= 10:00` | `int(100 - 25 * minutes_since_10 / 420)` |
| 10:00–16:59 | `L <= 03:00` 또는 None | 0 |
| 17:00–19:59 | `L > 17:00` | 100 |
| 17:00–19:59 | `10:00 < L <= 17:00` | `int(100 - 25 * minutes_since_17 / 180)` |
| 17:00–19:59 | `03:00 < L <= 10:00` | `int(75 - 25 * minutes_since_17 / 180)` |
| 17:00–19:59 | `L <= 03:00` 또는 None | 0 |
| 20:00–23:59 | `L > 20:00` | 100 |
| 20:00–23:59 | `17:00 < L <= 20:00` | `int(100 - 25 * minutes_since_20 / 240)` |
| 20:00–23:59 | `10:00 < L <= 17:00` | `int(75 - 25 * minutes_since_20 / 240)` |
| 20:00–23:59 | `03:00 < L <= 10:00` | `int(50 - 25 * minutes_since_20 / 240)` |
| 20:00–23:59 | `L <= 03:00` 또는 None | 0 |

비교 연산자는 표와 같이 strict `>`를 사용한다. 따라서 `L`이 시간대 시작과 정확히 같으면 다음 `elif` 분기로 들어간다.

선형식에서는 먼저 Python `int()`를 적용해 0 방향으로 절삭한 뒤 `max(0, min(100, score))`로 clamp한다. 계산 결과를 clamp한 후 `score`, `irCount`, `pirCount`에 동일하게 반영한다. 정상 계산 중 `temperature`, `humidity`, `light`는 100을 유지한다. 최종 destination의 `risk_score`를 만들 때도 `int(score)`를 사용한다.

Daily 문서가 없으면 Production과 동일하게 모든 점수를 30으로 설정한다.

```text
score = temperature = humidity = light = irCount = pirCount = 30
device_has_signal = False
user_is_out = False
```

Production 근거: `analyze_utils.py:get_time_of_day()`, 상수 `AFTER_MIDNIGHT_TIME`부터 `BEFORE_MIDNIGHT_TIME`, `analyze_user_stats()`의 각 시간대 분기.

## 12. Risk level

Production `models.scoreToRiskLevel()`과 동일한 경계를 사용한다.

| score | risk level |
|---:|---|
| 0–25 | `DANGER` |
| 26–50 | `ALERT` |
| 51–75 | `CAUTION` |
| 76–100 | `STABLE` |
| None 또는 0–100 밖 | `UNKNOWN` |

경계 검증값은 다음과 같다.

- 25 → `DANGER`
- 26 → `ALERT`
- 50 → `ALERT`
- 51 → `CAUTION`
- 75 → `CAUTION`
- 76 → `STABLE`

동일 변환을 overall, brightness, humidity, movement, remote control, temperature score에 각각 적용한다.

Production 근거: `iot-server/lib/models.py:scoreToRiskLevel()`의 `np.linspace(0, 100, 5)`와 `np.digitize(..., right=True)`.

## 13. Ward state 초기화

각 대상 ward는 replay 시작 전에 다음 메모리 state를 갖는다.

```text
is_out = False
last_caution_check_date = None
last_caution_check_user = None
last_is_out_reason = None
danger_counts = start 이전 DANGER가 존재한 서로 다른 KST 날짜 수
last_danger_date = start 이전 마지막 DANGER의 KST 날짜
```

이전 DANGER가 없으면 `danger_counts=0`, `last_danger_date=None`이다. DANGER 날짜 수와 마지막 날짜는 `ansimk.analysis_wardevaluation`을 SELECT해서 ward별로 계산한다. `evaluated_at < start_datetime` 조건을 엄격히 적용하고 날짜는 `Asia/Seoul` calendar date로 변환한다.

현재 `ansimk.resources_ward`를 초기값으로 읽거나 변경하지 않는다. 초기 query 결과에서 `danger_counts >= 7`인데 `last_danger_date=None`인 조합은 일관되지 않은 state다.

Production 근거: `analyze_utils.py:get_ward_status_for_risk_management()`가 읽는 여섯 필드. Recovery는 mutable Production snapshot 대신 위 초기화 정책을 사용한다.

## 14. Ward state 전이

평가는 evaluated_at 오름차순으로 수행하고, 동일 ward의 메모리 state를 다음 평가로 전달한다.

메모리 필드:

- `is_out`
- `last_caution_check_date`
- `last_caution_check_user`
- `last_is_out_reason`
- `danger_counts`
- `last_danger_date`

이 state는 destination 컬럼으로 저장하지 않고 `ansimk.resources_ward`에도 기록하지 않는다.

`is_out=True`일 때 Production 순서를 다음과 같이 재현한다.

1. 같은 KST 날짜에 `관리자`가 `자동 주시 전환`한 state이고 `T.hour >= 12`이면 메모리 `is_out=False`로 만든 뒤 일반 계산으로 진행한다.
2. 위 강제 해제 대상이 아니고 `L is None`이면 모든 점수를 70으로 반환한다.
3. 위 강제 해제 대상이 아니고 마지막 반응 후 경과가 30분을 초과하면 모든 점수를 70으로 반환한다.
4. 마지막 반응이 정확히 30분 이내이면 메모리 `is_out=False`로 만든 뒤 일반 계산으로 진행한다.

70점 분기의 공통값은 `device_has_signal=True`, `user_is_out=True`이고 모든 component score도 70이다. 실제 `resources_ward UPDATE`는 수행하지 않는다.

Production 근거: `analyze_utils.py:analyze_user_stats()`의 `is_out` branch와 `set_ward_is_out_false()` 호출. Recovery는 UPDATE를 메모리 변경으로 대체한다.

## 15. 자동 주시 전환

자동 주시 여부는 현재 DANGER를 누적하기 **이전** 메모리 state로 판단한다.

조건:

- MORNING 정상 계산 결과가 `DANGER`
- `danger_counts >= 7`
- `last_danger_date < evaluated_at의 KST 날짜`

`danger_counts >= 7`인데 `last_danger_date is None`이면 inconsistent state warning을 기록하고 자동 주시 전환을 수행하지 않는다. 비교 오류로 전체 replay를 중단하지 않는다.

조건 충족 시 원래 DANGER row를 유지하면서 메모리 state를 다음과 같이 바꾼다.

```text
is_out = True
last_caution_check_date = evaluated_at의 KST 날짜
last_caution_check_user = "관리자"
last_is_out_reason = "자동 주시 전환"
```

생성 row:

1. `evaluated_at`의 원래 `DANGER` row
2. `evaluated_at + 1초`의 모든 score 70인 `CAUTION` row

두 번째 row는 overall과 다섯 component가 모두 70이고 `device_has_signal=True`, `user_is_out=True`, reason은 `자동 주시 전환`이다. 이 `+1초` row는 정규 5분 evaluated_at 시계열을 추가로 진행시키지 않는다.

Production 근거: `analyze_utils.py:analyze_user_stats()`의 MORNING DANGER/autoset branch, `analyze_user_stats.py:consumer_thread_impl()`의 `_autoset_timestamp = scores['timestamp'] + timedelta(seconds=1)` 및 `autoset_scores` 생성.

## 16. DANGER 누적

처리 순서는 다음과 같이 고정한다.

1. 누적 전 state로 자동 주시 조건을 판단한다.
2. 원래 evaluated_at row를 생성한다.
3. 원래 row가 `DANGER`이면 danger state를 갱신한다.
4. 자동 주시가 발생했다면 별도의 `+1초` CAUTION row를 생성한다. 이 row는 DANGER 누적 대상이 아니다.

해당 KST 날짜의 첫 DANGER일 때만 다음을 수행한다.

```text
danger_counts += 1
last_danger_date = evaluated_at의 KST 날짜
```

같은 날짜의 추가 DANGER는 count를 증가시키지 않는다. Chronological replay에서 `last_danger_date == current_date`인지 확인하면 같은 날 중복 누적을 방지할 수 있다.

Production Python 함수는 현재 누적 전 state로 autoset을 판단하고, DANGER 누적은 PostgreSQL trigger가 수행하는 것으로 추정된다. Recovery는 Production trigger를 복사하거나 실행하지 않고 같은 순서를 Python 메모리에서 명시적으로 재현한다.

Production 근거: `analyze_utils.py:analyze_user_stats()`의 `danger_counts` 검사 순서. Trigger의 정확한 함수 본문은 repository에서 확인되지 않았다.

## 17. Note

Production `lib.analysis.note_on_time_variable_scores(scores)`의 분기 순서를 재현한다.

최소 scores 구조:

- 항상: `score`, `device_has_signal`, `user_is_out`
- out/caution: `last_is_out_reason`
- 사용자 지정 out reason: `elapsed_day_from_last_caution_check_date_as_day`, `last_caution_check_user`
- 일반 평가: `pirCount_meta.elapsed_time_from_last_vital_sign_timestamp_as_minutes`, `pirCount_meta.time_of_day`

주요 분기:

1. daily 문서가 없어 `device_has_signal=False`이면 전원/신호 확인 문구를 생성한다.
2. `user_is_out=True`이면 마지막 out reason에 따라 외출, 일반 사항, 자동 주시, 관리자 지정 사유 문구를 생성한다.
3. 일반 평가에서 elapsed time을 알 수 없으면 risk level별로 경과 시간을 알 수 없다는 문구를 생성한다.
4. elapsed time이 있으면 분 단위 값을 `int()`로 절삭하여 일·시간·분 문구를 만든다. DANGER/ALERT는 경과 시간을 직접 표시하고, CAUTION/STABLE은 움직임 상태 문구를 생성한다.
5. AFTER_MIDNIGHT의 STABLE note는 수면 시간대 특례 문구를 사용한다.
6. 자동 주시 `+1초` row는 `user_is_out=True`, `last_is_out_reason="자동 주시 전환"`으로 AI 자동 주시 문구를 생성한다. 이 분기는 `pirCount_meta`보다 먼저 반환된다.

측정된 temperature, humidity, illumination 값은 현재 note 함수의 직접 입력이 아니다.

Production 근거: `iot-server/lib/analysis.py:note_on_time_variable_scores()`, `convert_minutes_to_dhm()`, `format_dhm_string()`, `format_dday_string()`.

## 18. PostgreSQL 저장

Recovery는 계산 결과를 `archive.analysis_wardevaluation`에 직접 batch INSERT한다.

- 입력 순서는 기본 evaluated_at 오름차순을 유지한다.
- 일반 row와 자동 주시 `+1초` row 모두 동일한 10개 계산 컬럼 mapping을 사용한다.
- `id`는 destination default/sequence에 맡긴다.
- unique key는 `(ward_id, evaluated_at)`이다.
- conflict는 `DO NOTHING`으로 처리하고 skip 수를 검증 통계에 포함한다.
- destination write transaction은 Recovery 결과에만 한정한다.
- source SELECT와 MongoDB read를 write transaction이나 분산 transaction으로 묶지 않는다.

Recovery table에는 다음을 복사하지 않는다.

- `ansimk.resources_ward` foreign key
- `trg_auto_release_on_stable`
- `trg_increase_daily_danger`
- 기타 Production trigger

Production 근거: `lib.analysis.py:upsert_wardevalutions()`의 column mapping과 conflict policy. Production의 ward validation SELECT, Kafka 전달, notifier 후속 처리는 Recovery에서 사용하지 않는다.

## 19. 안전 제한

Recovery 설계와 스크립트는 다음을 절대 수정하지 않는다.

### PostgreSQL

- `archive.resources_measurement`
- `ansimk.resources_ward`
- `ansimk.resources_location`
- `ansimk.analysis_wardevaluation`
- 기존 Production 테이블 전체

### MongoDB

- `safeguard-staging.device-daily`
- `safeguard-staging`의 다른 collection
- 기존 Production MongoDB database와 collection

### repository 파일

- Production 코드 전체
- `rebuild_device_daily.py`
- `postgres.py`
- `mongodb.py`
- `.env`
- `pyproject.toml`
- `uv.lock`
- test 파일
- 기존 Markdown 문서

새 Recovery 구현은 Production 모듈을 import하거나 호출하지 않는다. 특히 `analyze_utils`, `analyze_user_stats`, `analyze_write_db`, `lib.analysis`, `lib.postgres`, `lib.mongo`, `notifier`는 import 시에도 DB pool/DDL, MongoDB client/index, Kafka publish 등의 side effect가 발생할 수 있다. 필요한 공식과 순수 note 로직만 독립적으로 이식한다.

유일한 향후 write 대상은 `archive.analysis_wardevaluation`이다. 문서 작성 단계에서는 이 테이블도 변경하지 않는다.

## 20. 검증

Recovery 구현은 dry-run과 실제 실행 모두에서 최소한 다음을 집계·검증해야 한다.

- normalized start/end와 생성한 정규 evaluated_at 수
- 대상 distinct ward 수
- `(ward_id, evaluated_at)` 평가 조합 수
- `device-daily` 문서 없음 수
- latest timestamp 다중 IMEI 후보 발생 수
- 다중 후보에서 선택한 non-null vital 값과 후보 수
- DANGER/ALERT/CAUTION/STABLE/UNKNOWN row 수
- 자동 주시 전환 횟수와 `+1초` row 수
- ward별 초기 `danger_counts`, `last_danger_date` 산출 결과
- 날짜별 첫 DANGER 누적 수와 같은 날 중복 DANGER skip 수
- inconsistent state warning 수
- destination insert 예정 수, 실제 insert 수, conflict skip 수, 실패 수
- risk 경계 25/26/50/51/75/76 테스트
- 시간대 경계 03:00/10:00/17:00/20:00 및 `L`이 경계와 같은 경우 테스트
- `last_vital_sign_timestamp`가 None인 각 branch 테스트
- 자동 주시 당일 12:00 해제와 정확히 30분/30분 초과 branch 테스트

샘플 ward와 기존 `ansimk.analysis_wardevaluation`의 겹치는 기간을 비교할 수 있지만, 기존 테이블은 reference SELECT로만 사용한다. 차이는 Production/Recovery 정책 차이, archive 원천 차이, 과거 state 부재로 분류해 기록한다.

## 21. 알려진 한계

- 과거 수동 외출 및 복귀 이력은 복원할 수 없다.
- 병원 입원, 전원 분리, 기기 위치 변경 이력은 복원하지 않는다.
- archive measurement의 `ward_id`와 `imei`를 그대로 신뢰하므로 현재 설치 정보와의 불일치를 교정하지 않는다.
- archive 범위에 measurement가 없는 ward는 대상에서 제외되어 과거 신호 없음 evaluation이 누락될 수 있다.
- Production `device_daily`와 Recovery `device-daily` 데이터가 완전히 동일하지 않을 수 있다.
- 당시 MongoDB 원본 telemetry와 `archive.resources_measurement` 사이에 차이가 있을 수 있다.
- 당시 실행된 Production 코드 버전과 현재 분석한 코드가 완전히 동일하지 않을 수 있다.
- 시작 이전 수동 ward state는 완전히 복원할 수 없으며 이 문서의 초기화 정책을 따른다.
- 동일 latest daily timestamp에 여러 IMEI가 있으면 Recovery는 최신 non-null vital을 선택하므로 Production의 비결정적 단일 문서 선택 결과와 다를 수 있다.
- Production trigger 본문과 과거 trigger 버전이 확인되지 않아 danger 누적은 확정 Recovery 정책으로 재현한다.
- destination의 실제 컬럼 타입, default, sequence와 unique constraint는 구현 전 read-only schema 확인이 필요하다.

## 22. Production 코드 근거

| 규칙 | Production/Recovery 근거 |
|---|---|
| Production ward 대상 | `iot-server/analyze_utils.py:get_all_installed_ward_ids()` |
| 5분 scheduler와 시작 정렬 | `iot-server/analyzer_user_stats_producer.py:user_stats_worker()` |
| Production `device_daily` lookup | `iot-server/analyze_utils.py:analyze_user_stats()` |
| Production daily vital 생성 | `iot-server/analyze_utils.py:analyze_device_daily_device()` |
| 시간대 정의와 공식 | `iot-server/analyze_utils.py:get_time_of_day()`, `analyze_user_stats()` |
| is_out 및 autoset 순서 | `iot-server/analyze_utils.py:analyze_user_stats()` |
| Production ward UPDATE | `set_ward_is_out_false()`, `autoset_ward_is_out_true()`; Recovery에서는 호출 금지 |
| `+1초` CAUTION row | `iot-server/analyze_user_stats.py:consumer_thread_impl()` |
| Risk level 경계 | `iot-server/lib/models.py:scoreToRiskLevel()` |
| Note | `iot-server/lib/analysis.py:note_on_time_variable_scores()` |
| Destination column mapping | `iot-server/analyze_user_stats.py:consumer_thread_impl()` |
| Production insert/conflict | `iot-server/lib/analysis.py:upsert_wardevalutions()` |
| Kafka write path와 notifier | `iot-server/analyze_write_db.py:consumer_thread_impl()`, `analyze_utils.py:produce_analysis_from_user_stats_batch()` |

### Recovery implementation reference

| 규칙 | Recovery 근거 |
|---|---|
| Recovery `device-daily` 선택 | `rebuild_device_daily.py:main()` |
| Archived ward/IMEI 직접 사용 | `rebuild_device_daily.py:load_groups()` |
| Recovery daily vital 생성 | `rebuild_device_daily.py:build_document()` |

Production 코드는 원래 동작을 확인하는 근거다. Collection 이름, ward 선정, multi-IMEI 선택, state 초기화·전이, trigger 대체, destination에 대해서는 이 Recovery 문서의 규칙이 우선한다.
