import json
from types import SimpleNamespace

import pytest

from workflows.ax768 import information_extraction as flow

TEXT = "이름: 테스트가입자\n보호자: 테스트보호자\n연락처: 010-0000-1234\n기기 S/N: 00300016\n변경 요청: 연락처 수정"
FIELDS = [
    {"label": label, "value": value, "source_index": 0, "uncertain": False}
    for label, value in [
        ("가입자 이름", "테스트가입자"),
        ("보호자 이름", "테스트보호자"),
        ("보호자 연락처", "010-0000-1234"),
        ("S/N", "00300016"),
        ("요청", "연락처 수정"),
    ]
]
BODY = {
    "workflow_id": "information_update",
    "extraction_version": "1",
    "sources": [{"text": TEXT}],
}


def mock_model(monkeypatch, fields=FIELDS, finish="stop", error=None):
    calls = []

    class Model:
        def __init__(self, settings):
            assert settings.max_attempts == 1

        async def complete_structured(self, messages, **kwargs):
            calls.append((messages, kwargs))
            if error:
                raise error
            return SimpleNamespace(
                text=json.dumps({"fields": fields}), finish_reason=finish
            )

        async def aclose(self):
            calls.append("closed")

    monkeypatch.setenv("OPENAI_BASE_URL", "http://local-model.test/v1")
    monkeypatch.setenv("OPENAI_MODEL", "existing-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(flow, "OpenAICompatibleChatModel", Model)
    return calls


@pytest.mark.asyncio
async def test_graph_extracts_open_fields_without_tools(monkeypatch):
    calls = mock_model(monkeypatch)
    result = await flow.graph.ainvoke(BODY)
    assert result["status"] == "completed" and result["fields"] == FIELDS
    assert result["error"] is None
    messages, kwargs = calls[0]
    assert json.loads(messages[1]["content"]) == [{"source_index": 0, "text": TEXT}]
    assert "untrusted" in messages[0]["content"]
    assert kwargs["temperature"] == 0 and len(calls) == 2 and calls[-1] == "closed"
    assert (
        flow.graph.get_input_jsonschema()["properties"]["extraction_version"]["const"]
        == "1"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"value": "invented"},
        {"source_index": 1},
        {"source_index": True},
        {"label": " "},
        {"value": " "},
        {"uncertain": "false"},
        {"tool": "update_member"},
    ],
)
async def test_rejects_ungrounded_or_invalid_values(monkeypatch, change):
    mock_model(monkeypatch, [{**FIELDS[0], **change}])
    result = await flow.extract(BODY)
    assert result["status"] == "failed" and result["fields"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finish,error",
    [
        ("length", None),
        ("content_filter", None),
        ("stop", TimeoutError()),
        ("stop", flow.ModelRequestError("private-secret", retryable=True)),
    ],
)
async def test_failure_clears_stale_fields_and_does_not_retry(
    monkeypatch, finish, error
):
    calls = mock_model(monkeypatch, finish=finish, error=error)
    result = await flow.extract({**BODY, "fields": FIELDS, "status": "completed"})
    assert result["status"] == "failed" and result["fields"] == []
    assert "private-secret" not in str(result) and len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"workflow_id": "device_adjustment_power"},
        {"extraction_version": "0"},
        {"sources": []},
        {"sources": [{"text": " "}]},
        {"sources": [{"text": "x" * 8001}]},
        {"sources": [{"text": "x"}] * 7},
    ],
)
async def test_invalid_input_never_calls_model(monkeypatch, change):
    calls = mock_model(monkeypatch)
    assert (await flow.extract({**BODY, **change}))["status"] == "failed"
    assert calls == []


def test_separate_sources_conflicting_values_and_literal_identifiers():
    sources = [
        flow.Source(text="기존 연락처 010-0000-1111"),
        flow.Source(text="변경 연락처 010-0000-2222"),
    ]
    data = flow.Extraction(
        fields=[
            flow.ExtractedField(
                label="기존 연락처",
                value="010-0000-1111",
                source_index=0,
                uncertain=True,
            ),
            flow.ExtractedField(
                label="변경 연락처",
                value="010-0000-2222",
                source_index=1,
                uncertain=True,
            ),
        ]
    )
    flow.validate_grounding(data, sources)
    assert len(data.fields) == 2 and all(item.uncertain for item in data.fields)


def test_chunks_cover_all_input_with_original_source_indices():
    text = ("기타 참고사항: " + "가나다라마바사" * 250 + "\n") * 4
    sources = [flow.Source(text=text), flow.Source(text="연락처 010-0000-1234")]
    chunks = list(flow.source_chunks(sources))
    assert all(len(chunk["text"]) <= 1000 for chunk in chunks)
    assert chunks[-1] == {"source_index": 1, "text": sources[1].text}
    # Every source character is covered, including a long line spanning chunks.
    cursor = 0
    for chunk in chunks[:-1]:
        start = text.find(chunk["text"], max(0, cursor - 100))
        assert 0 <= start <= cursor
        cursor = start + len(chunk["text"])
    assert cursor == len(text)


@pytest.mark.asyncio
async def test_parallel_chunks_remain_bounded_and_fail_atomically(monkeypatch):
    import asyncio

    calls = mock_model(monkeypatch)
    active = peak = 0

    async def complete(self, messages, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            assert kwargs["max_tokens"] == 3500
            await asyncio.sleep(0)
            chunk = json.loads(messages[1]["content"])[0]
            if "FAIL" in chunk["text"]:
                raise flow.ModelRequestError("provider", retryable=False)
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "fields": [
                            {
                                "label": "메모",
                                "value": chunk["text"],
                                "source_index": chunk["source_index"],
                                "uncertain": False,
                            }
                        ]
                    }
                ),
                finish_reason="stop",
            )
        finally:
            active -= 1

    monkeypatch.setattr(flow.OpenAICompatibleChatModel, "complete_structured", complete)
    body = {**BODY, "sources": [{"text": ("메모\n" * 700) + "FAIL"}]}
    result = await flow.extract(body)
    assert result["status"] == "failed" and result["fields"] == []
    assert peak == 2 and active == 0 and calls == ["closed"]


def test_subject_name_expansion_requires_direct_body_evidence():
    sources = [
        flow.Source(
            text="박민수\n테스트항길 50-1\n김하늘님\n박민수에게 답장\n이도윤님\n010-0000-1111"
        )
    ]
    fields = [
        flow.ExtractedField(
            label="김하늘 · 주소",
            value="테스트항길 50-1",
            source_index=0,
            uncertain=False,
        ),
        flow.ExtractedField(
            label="이도윤 · 전화번호",
            value="010-0000-1111",
            source_index=0,
            uncertain=True,
        ),
        flow.ExtractedField(
            label="박민수 · 기타",
            value="박민수에게 답장",
            source_index=0,
            uncertain=True,
        ),
        flow.ExtractedField(
            label="없는이름 · 기타",
            value="박민수에게 답장",
            source_index=0,
            uncertain=True,
        ),
    ]
    result = flow.include_subject_names(fields, sources)
    names = [field for field in result if field.label.endswith(" · 이름")]
    assert [(field.value, field.uncertain) for field in names] == [
        ("김하늘", False),
        ("이도윤", True),
    ]
    flow.validate_grounding(flow.Extraction(fields=result), sources)
    assert result[0].label == "김하늘 · 이름"


def test_subject_name_expansion_does_not_duplicate_or_cross_sources():
    sources = [
        flow.Source(text="대상자: 김하늘\n주소: 테스트로 1"),
        flow.Source(text="박민수\n메모"),
    ]
    fields = [
        flow.ExtractedField(
            label="김하늘 · 주소", value="테스트로 1", source_index=0, uncertain=False
        ),
        flow.ExtractedField(
            label="김하늘 · 이름", value="김하늘", source_index=0, uncertain=False
        ),
        flow.ExtractedField(
            label="김하늘 · 기타", value="메모", source_index=1, uncertain=True
        ),
    ]
    assert flow.include_subject_names(fields, sources) == fields
    assert flow.include_subject_names([fields[0]], sources)[0].value == "김하늘"


@pytest.mark.asyncio
@pytest.mark.parametrize("repair_succeeds", [True, False])
async def test_sender_assignment_is_repaired_once_or_rejected(
    monkeypatch, repair_succeeds
):
    calls = mock_model(monkeypatch)
    responses = []

    async def complete(self, messages, **kwargs):
        responses.append(messages)
        subject = "김하늘" if repair_succeeds and len(responses) == 2 else "박민수"
        return SimpleNamespace(
            text=json.dumps(
                {
                    "fields": [
                        {
                            "label": subject + " · 주소",
                            "value": "테스트항길 50-1",
                            "source_index": 0,
                            "uncertain": False,
                        }
                    ]
                }
            ),
            finish_reason="stop",
        )

    monkeypatch.setattr(flow.OpenAICompatibleChatModel, "complete_structured", complete)
    source = "박민수\n테스트항길 50-1\n김하늘님\n박민수에게 답장"
    result = await flow.extract({**BODY, "sources": [{"text": source}]})
    assert len(responses) == 2 and calls == ["closed"]
    assert json.loads(responses[0][1]["content"])[0]["chat_context"] == {
        "reply_sender_headers": ["박민수"],
        "body_name_lines": ["김하늘"],
    }
    if repair_succeeds:
        assert result["status"] == "completed"
        assert [(item["label"], item["value"]) for item in result["fields"]] == [
            ("김하늘 · 이름", "김하늘"),
            ("김하늘 · 주소", "테스트항길 50-1"),
        ]
    else:
        assert result["status"] == "failed" and result["fields"] == []


def test_sender_can_also_be_explicit_subject_or_assigned_staff():
    field = flow.ExtractedField(
        label="박민수 · 주소", value="테스트로 1", source_index=0, uncertain=False
    )
    assert not flow.assigns_sender_as_subject(
        [field], "박민수에게 답장\n대상자: 박민수\n테스트로 1"
    )
    assert flow.assigns_sender_as_subject(
        [field], "박민수에게 답장\n김하늘님\n테스트로 1"
    )
    staff = flow.ExtractedField(
        label="담당자", value="박민수", source_index=0, uncertain=False
    )
    assert not flow.assigns_sender_as_subject(
        [staff], "박민수에게 답장\n담당자: 박민수"
    )
