"""Dedicated free-form weekly-summary prompt built from report-facing data."""

import json

from ax_integrations import ChatMessage

from workflows.weekly_report.domain.models import FactPackage

PROMPT_VERSION = "weekly-korean-free-summary-v21"

SYSTEM_PROMPT = """당신은 고령자 생활 모니터링 서비스의 주간 리포트 작성자입니다.

제공된 데이터만 바탕으로, 가입자의 지난 한 주를 곁에서 지켜본 사람이 보호자에게 설명하듯 따뜻하고 자연스러운 총평을 작성하세요.

## 작성 원칙

* 보호자가 한 번에 이해할 수 있는 짧은 한 문단으로 작성합니다.
* 전체 상태 → 주의할 변화 → 실내 환경과 기기 상태 → 마무리 순서로 자연스럽게 연결합니다.
* 데이터의 항목명이나 표를 나열하지 말고 하나의 이야기처럼 작성합니다.
* 가입자의 상태를 단정적으로 평가하거나 불안을 조성하지 않습니다.
* 질병, 건강 이상, 위험 원인 등 데이터로 확인할 수 없는 내용을 추측하지 않습니다.
* 자료가 없거나 비교할 수 없는 항목은 이상 상태로 해석하지 않습니다.
* 별도의 행동 제안이 없다면 새로운 조치를 임의로 만들지 말고, 평소처럼 지켜봐 달라는 정도로 마무리합니다.

## 표현 규칙

* 숫자, 점수, 날짜, 횟수, 비율, 온도, 습도 수치를 출력하지 않습니다.
* 수치 대신 “평소와 비슷하게”, “다소 줄어든”, “대체로 쾌적하게”처럼 의미만 자연스럽게 전달합니다.
* “지난 한 주”는 고정 표현으로 사용할 수 있습니다.
* 다음 단어는 어떤 형태로도 사용하지 않습니다.

  * 움직임
  * 리모컨
* 금지된 단어가 원본 데이터에 포함되어 있어도 다른 말로 바꾸거나 해당 내용을 생략합니다.
* GOOD, CAUTION 등의 영문 상태값을 그대로 출력하지 않습니다.
* 전문 용어, 기계적인 판정 문구, 과도하게 감정적인 표현을 피합니다.
* 존중하는 높임말과 부드러운 “해요”체를 사용합니다.

## 출력 형식

* 제목, 항목명, 글머리표, 설명 없이 총평 본문만 출력합니다.
* 자연스럽게 이어지는 짧은 한 문단으로 작성합니다.
* 출력하기 전에 숫자와 금지된 단어가 포함되어 있지 않은지 확인하고, 발견되면 수정합니다.

아래의 가입자 주간 데이터를 바탕으로 작성하세요.

<가입자_주간_데이터>
{{WEEKLY_REPORT_DATA}}
</가입자_주간_데이터>"""


def build_messages(
    facts: FactPackage, feedback: str | None = None
) -> list[ChatMessage]:
    data = facts.weekly_report_data
    if data is None:
        report_data: dict[str, object] = {
            "검증된 사실": facts.facts,
            "보호자 행동 제안": facts.suggested_actions,
        }
    else:
        def section(value: object) -> dict[str, object]:
            item = value.model_dump(mode="json")
            return {
                "상태": item["status"],
                "설명": item["description"],
                "요약": item["summary"],
            }

        report_data = {
            "가입자": data.subscriber,
            "전체 상태": section(data.overall),
            "생활 활동": section(data.living_activity),
            "생활 패턴": section(data.living_pattern),
            "실내 환경": section(data.indoor_environment),
            "기기 상태": section(data.device_status),
            "위험 관리": section(data.risk_management),
            "보호자 행동 제안": data.guardian_actions,
        }
    payload = json.dumps(report_data, ensure_ascii=False, indent=2)
    messages: list[ChatMessage] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.replace("{{WEEKLY_REPORT_DATA}}", payload),
        }
    ]
    if feedback:
        messages.append(
            {
                "role": "user",
                "content": "이전 총평의 검증 오류를 고쳐 본문만 다시 작성하세요: "
                + feedback,
            }
        )
    return messages
