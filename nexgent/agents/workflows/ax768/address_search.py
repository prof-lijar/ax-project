"""User-facing search and verified row-highlight results for case 2.2."""


def result_message(result):
    override_note = ""
    if result.get("overridden_cells"):
        override_note = (
            " 저장된 노란색과 화면 표시 색상이 다른 셀: "
            + ", ".join(result["overridden_cells"])
            + ". 기존 조건부 서식 등을 확인하세요."
        )
    if "name" in result:
        query = f"{result['name']} / {result['query']}"
        if result["status"] == "not_found":
            return f"'{query}' 이름과 주소가 같은 행을 찾지 못했습니다."
        if result["status"] == "highlighted_with_warnings":
            return (
                f"'{query}' 최신 일치 행: {result['selected_row']}행. "
                f"{result['highlighted_range']} 행 전체의 노란색 배경 저장을 확인했습니다."
                + override_note
            )
        if not result["verified"]:
            return (
                f"'{query}' {result['selected_row']}행을 찾았으나 노란색 표시를 확인하지 못했습니다."
                + override_note
            )
        return (
            f"'{query}' 최신 일치 행: {result['selected_row']}행. "
            f"{result['highlighted_range']} 행 전체를 노란색으로 표시하고 확인했습니다."
        )
    if result["status"] == "not_found":
        return f"'{result['query']}' 주소와 일치하는 행을 찾지 못했습니다."
    lines = [
        f"'{result['query']}' 주소 검색: {result['match_count']}개 행. 가장 아래 행: {result['selected_row']}행."
    ]
    if result["status"] == "highlighted":
        lines.append(
            f"{result['highlighted_range']} 행 전체를 노란색으로 표시하고 확인했습니다."
        )
    elif result["status"] == "highlighted_with_warnings":
        lines.append(
            f"{result['highlighted_range']} 행 전체의 노란색 배경 저장을 확인했습니다."
            + override_note
        )
    elif result["status"] == "verification_failed":
        lines.append(
            "행 배경색 변경을 요청했지만 노란색 표시를 확인하지 못했습니다."
            + override_note
        )
    for match in result["matches"]:
        addresses = "; ".join(
            f"{cell['cell']}: {cell['address']}" for cell in match["cells"]
        )
        lines.append(f"{match['row']}행 — {addresses}")
    return "\n".join(lines)
