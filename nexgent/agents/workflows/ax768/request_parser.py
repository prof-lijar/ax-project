"""Deterministic extraction for one Korean service request; never fixes a name."""

import re
import unicodedata

ROAD = re.compile(r"[가-힣0-9·.]+(?:로|길)\s*\d+(?:\s*-\s*\d+)?")


def compact_name(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value)))


def parse_request(message):
    if not isinstance(message, str) or not 0 < len(message.strip()) <= 8000:
        raise ValueError("이름과 주소가 포함된 요청을 1~8,000자로 입력해 주세요.")
    text = unicodedata.normalize("NFKC", message).strip(" \t\r\n\"'“”‘’")
    text = re.sub(r"^\d+[.)]?\s+(?=[가-힣])", "", text)
    # Circled enumeration becomes a leading digit without a space under NFKC.
    if message.lstrip()[:1] in "①②③④⑤⑥⑦⑧⑨":
        text = re.sub(r"^\d+\s*", "", text)
    addresses = list(ROAD.finditer(text))
    if len(addresses) > 1:
        raise ValueError("한 번에 한 사람의 이름과 주소를 입력해 주세요.")
    road = addresses[0] if addresses else None
    address = re.sub(r"\s*-\s*", "-", road.group()) if road else None
    if address:
        address = re.sub(r"(?<=[로길])\s*(?=\d)", " ", address)
    honorifics = list(re.finditer("님", text))
    if len(honorifics) > 1:
        raise ValueError("한 번에 한 사람의 요청만 입력해 주세요.")
    if honorifics:
        end = honorifics[0].start()
        name = text[road.end() : end] if road and road.end() <= end else text[:end]
    elif road:
        suffix = text[road.end() :].strip()
        name = suffix.split(",")[1] if suffix.startswith(",") else suffix.split(",")[0]
    else:
        # A standalone Korean name needs no honorific or request suffix.
        # Keep free-form instructions out of the name field: only the known
        # signal-check suffix is accepted when additional words are present.
        match = re.fullmatch(
            r"([가-힣]{2,5})(?:\s+신호\s*확인\s*(?:요|해주세요|해\s*주세요|부탁드립니다)?[.!?。~]*)?",
            text,
        )
        if not match:
            raise ValueError(
                "이름을 확인할 수 없습니다. 예: '김순옥' 또는 '울진북로 164 김순옥님 신호확인요.'"
            )
        name = match.group(1)
    name = compact_name(name.strip(" ,&"))
    if not re.fullmatch(r"[가-힣]{2,10}", name):
        raise ValueError("이름을 확인할 수 없습니다. 주소 뒤에 이름을 입력해 주세요.")
    if not address and "사진" in text:
        raise ValueError("사진에 있는 주소를 텍스트로 함께 입력해 주세요.")
    return {
        "name": name,
        "address": address,
        "mode": "name_address" if address else "name_only",
    }
