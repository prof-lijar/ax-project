"""Explicit Korean signal-check shorthand maps to a constrained sheet action."""

import re


def requested_name(message: str) -> str | None:
    match = re.fullmatch(
        r"\s*([가-힣]{2,10})\s*님\s*신호\s*확인\s*(?:요|해주세요|해\s*주세요|부탁드립니다)?[.!?。]*\s*",
        message,
    )
    return match.group(1) if match else None


def result_message(result):
    name = result["name"]
    if result["status"] == "not_found":
        return f"{name}님 이름을 지정된 시트에서 찾지 못했습니다. 변경한 셀은 없습니다."
    cells = ", ".join(result["matched_cells"])
    if result["status"] == "found":
        return f"{name}님 최신 일치 행: {result['selected_row']}행. 이름 셀: {cells}"
    if result["verified"]:
        return f"{name}님 이름 중 가장 아래 행의 셀을 노란색으로 표시하고 확인했습니다: {cells}"
    return f"{name}님 이름 셀에 노란색 배경을 적용했지만 표시 검증에 실패했습니다. 조건부 서식이나 동시 편집을 확인해 주세요: {cells}"
