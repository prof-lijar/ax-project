"""Deterministic production report coverage; never sends subscriber data."""

from datetime import date, timedelta

REGIONS = ("전체", "울진", "영덕", "광명", "기타")

# Match municipality tokens, not street/building names such as 광명로.
COVERAGE_SQL = """
WITH wards AS (
    SELECT id, CASE
      WHEN address ~ '(^|[[:space:]])울진군?([[:space:]]|$)' THEN '울진'
      WHEN address ~ '(^|[[:space:]])영덕군?([[:space:]]|$)' THEN '영덕'
      WHEN address ~ '(^|[[:space:]])광명시?([[:space:]]|$)' THEN '광명'
      ELSE '기타' END AS region
    FROM ansimk.resources_ward
    WHERE has_device IS NOT FALSE
), weeks(week_start) AS (VALUES ($1::date), ($1::date - 7)),
coverage AS (
    SELECT w.region, p.week_start, EXISTS (
        SELECT 1 FROM ansimk.resources_ward_weekly_report r
        WHERE r.ward_id = w.id AND r.week_start_date = p.week_start
    ) AS success
    FROM wards w CROSS JOIN weeks p
)
SELECT week_start, region, count(*) AS total,
       count(*) FILTER (WHERE success) AS success
FROM coverage GROUP BY week_start, region
"""


async def collect_coverage(connection, week_start):
    if week_start.weekday() != 0:
        raise ValueError("coverage week must start on Monday")
    async with connection.transaction(isolation="repeatable_read", readonly=True):
        rows = await connection.fetch(COVERAGE_SQL, week_start)
    weeks = []
    for start in (week_start, week_start - timedelta(days=7)):
        groups = {region: {"total": 0, "success": 0} for region in REGIONS}
        for row in rows:
            if row["week_start"] == start:
                groups[row["region"]] = {key: row[key] for key in ("total", "success")}
        groups["전체"] = {
            key: sum(groups[region][key] for region in REGIONS[1:])
            for key in ("total", "success")
        }
        weeks.append({"week_start": start.isoformat(), "regions": groups})
    return {"version": 1, "weeks": weeks}


def notification_payload(snapshot, *, week_start, destination):
    """Validate the persisted aggregate boundary before formatting counts."""
    selected = date.fromisoformat(week_start)
    if (
        selected.weekday() != 0
        or snapshot["version"] != 1
        or len(snapshot["weeks"]) != 2
    ):
        raise ValueError("invalid coverage snapshot")
    rates = []
    periods = []
    for index, week in enumerate(snapshot["weeks"]):
        start = selected - timedelta(days=7 * index)
        if week["week_start"] != start.isoformat() or set(week["regions"]) != set(
            REGIONS
        ):
            raise ValueError("invalid coverage periods or regions")
        periods.append(
            f"{'지난주' if index == 0 else '2주 전'} ({start:%Y/%m/%d}~{start + timedelta(days=6):%m/%d})"
        )
        week_rates = {}
        for region in REGIONS:
            counts = week["regions"][region]
            total, success = counts["total"], counts["success"]
            if (
                any(type(n) is not int for n in (total, success))
                or not 0 <= success <= total
            ):
                raise ValueError("invalid coverage counts")
            failed = total - success
            rate = 100 * failed / total if total else None
            week_rates[region] = rate
        for key in ("total", "success"):
            if week["regions"]["전체"][key] != sum(
                week["regions"][r][key] for r in REGIONS[1:]
            ):
                raise ValueError("inconsistent coverage total")
        rates.append(week_rates)
    current = snapshot["weeks"][0]["regions"]["전체"]
    previous = snapshot["weeks"][1]["regions"]["전체"]
    missing = current["total"] - current["success"]
    previous_missing = previous["total"] - previous["success"]
    difference = missing - previous_missing
    if not current["total"]:
        summary = "집계 대상 가입자가 없습니다."
    else:
        change = (
            f"{abs(difference):,}명 {'증가' if difference > 0 else '감소'}"
            if difference
            else "변동 없음"
        )
        summary = f"지난주 누락 {missing:,}명 · 전주 대비 {change}"
    lines = [summary]
    if current["total"]:
        lines.append(
            f"가입자 {current['total']:,}명 중 {current['success']:,}명 저장 완료"
        )
    lines.extend(["", *periods])
    rows = []
    for region in REGIONS:
        current_rate, previous_rate = rates[0][region], rates[1][region]
        if current_rate is None or previous_rate is None:
            change = "비교 불가"
        else:
            delta = round(current_rate - previous_rate, 2)
            change = (
                f"{abs(delta):.2f}%p {'증가' if delta > 0 else '감소'}"
                if delta
                else "변동 없음 (0.00%p)"
            )
        for index, week in enumerate(snapshot["weeks"]):
            counts = week["regions"][region]
            rate = rates[index][region]
            rows.append(
                [
                    region,
                    "지난주" if index == 0 else "2주 전",
                    f"{counts['total']:,}",
                    f"{counts['success']:,}",
                    f"{counts['total'] - counts['success']:,}",
                    f"{rate:.2f}%" if rate is not None else "산정 불가",
                    change if index == 0 else "기준 주",
                ]
            )
    payload = {
        "destination": destination,
        "title": "주간 리포트 저장 현황",
        "severity": "warning" if missing else "success",
        "locale": "ko",
        "text": "\n".join(lines),
        "table": {
            "columns": [
                "지역",
                "주차",
                "가입자(명)",
                "성공(명)",
                "실패·누락(명)",
                "누락률",
                "전주 대비 누락률",
            ],
            "rows": rows,
            "align": ["left", "left", "right", "right", "right", "right", "right"],
        },
        "footer": (
            "집계 기준\n"
            "• 성공: 운영 DB에 해당 주 리포트가 있음 · 실패(누락): 리포트가 없음\n"
            "• 누락률 = 실패 ÷ 가입자 수 × 100 · 가입자 0명은 산정·비교 불가\n"
            "• 전주 대비 = 지난주 누락률 − 2주 전 누락률 · 감소할수록 개선\n"
            "• %p는 퍼센트포인트(두 비율의 차이) · 원자료로 계산 후 소수 둘째 자리 반올림\n"
            "• 두 주 모두 조회 시점의 동일한 가입자·주소 기준 · 미분류 주소는 기타\n"
            "• 과거 가입·탈퇴 및 주소 변경 이력 미반영 · 기존 저장 리포트도 성공에 포함"
        ),
    }

    table = payload["table"]
    return {
        "destination": destination,
        "severity": payload["severity"],
        "locale": "ko",
        "text": summary,
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": payload["title"]},
            },
            {
                "type": "section",
                "text": {"type": "plain_text", "text": "\n".join(lines[:2])},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "plain_text", "text": " · ".join(periods)},
                ],
            },
            {"type": "divider"},
            {
                "type": "table",
                "column_settings": [
                    {"align": align, "is_wrapped": True} for align in table["align"]
                ],
                "rows": [
                    [{"type": "raw_text", "text": cell} for cell in row]
                    for row in [table["columns"], *table["rows"]]
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "plain_text", "text": payload["footer"]},
            },
        ],
    }
