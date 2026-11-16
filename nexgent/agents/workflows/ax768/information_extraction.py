"""Tool-free, source-grounded extraction for the information-update workflow."""

import asyncio
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Literal, TypedDict

from ax_integrations.chat import (
    ModelRequestError,
    OpenAICompatibleChatModel,
    OpenAICompatibleSettings,
)
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, model_validator

PROMPT = (
    Path(__file__)
    .with_name("prompts")
    .joinpath("information_extraction.md")
    .read_text()
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Source(StrictModel):
    text: str = Field(min_length=1, max_length=8000)


class ExtractionRequest(StrictModel):
    workflow_id: Literal["information_update"]
    extraction_version: Literal["1"]
    sources: list[Source] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def nonblank(self):
        if any(not source.text.strip() for source in self.sources):
            raise ValueError("Empty source")
        return self


class ExtractedField(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=8000)
    source_index: int = Field(ge=0, le=5)
    uncertain: bool


class Extraction(StrictModel):
    fields: list[ExtractedField] = Field(max_length=200)


def name_evidence(name: str, text: str):
    literal = re.escape(name)
    return re.search(
        rf"(?m)^\s*(?:{literal}님|(?:이름|성명|대상자|가입자)(?:명)?\s*[:：]\s*{literal}(?:님)?)\s*$",
        text,
    )


def reply_senders(text: str):
    return set(re.findall(r"(?m)^\s*([가-힣]{2,5})에게[ \t]*답장[ \t]*$", text))


def chat_context(text: str):
    senders = reply_senders(text)
    if not senders:
        return None
    names = re.findall(r"(?m)^[ \t]*([가-힣]{2,5})님[ \t]*$", text)
    return {
        "reply_sender_headers": sorted(senders)[:20],
        "body_name_lines": list(dict.fromkeys(names))[:20],
    }


def assigns_sender_as_subject(fields: list[ExtractedField], text: str):
    excluded = {name for name in reply_senders(text) if not name_evidence(name, text)}
    for item in fields:
        subject, separator, _ = item.label.partition(" · ")
        if separator and subject.removesuffix("님").strip() in excluded:
            return True
        name = item.value.removesuffix("님").strip()
        if name in excluded and not re.search(
            rf"(?:담당자|현장관리자)\s*[:：]\s*{re.escape(name)}", text
        ):
            return True
    return False


def include_subject_names(fields: list[ExtractedField], sources: list[Source]):
    """Make subject-qualified labels explicit only with direct name evidence."""
    result = []
    seen = set()
    for item in fields:
        subject, separator, _ = item.label.partition(" · ")
        name = subject.removesuffix("님").strip()
        key = (item.source_index, subject)
        if separator and key not in seen and 1 < len(name) <= 100:
            seen.add(key)
            # A label alone is not name evidence. Require a body name line or
            # an explicit name field; repeated sender headers cannot qualify.
            evidence = name_evidence(name, sources[item.source_index].text)
            already_present = any(
                other.source_index == item.source_index
                and other.value in {name, name + "님"}
                and any(
                    word in other.label for word in ("이름", "성명", "대상자", "가입자")
                )
                for other in fields
            )
            if evidence and not already_present:
                result.append(
                    ExtractedField(
                        label=f"{subject} · 이름",
                        value=name,
                        source_index=item.source_index,
                        uncertain=item.uncertain,
                    )
                )
        result.append(item)
    return result


def validate_grounding(result: Extraction, sources: list[Source]) -> None:
    for item in result.fields:
        if (
            not item.label.strip()
            or not item.value.strip()
            or item.source_index >= len(sources)
            or item.value not in sources[item.source_index].text
        ):
            raise ValueError("Extracted value is not grounded in its source")
    if sum(len(item.label) + len(item.value) for item in result.fields) > 56000:
        raise ValueError("Extraction is too large")


class ExtractionInput(TypedDict):
    workflow_id: Literal["information_update"]
    extraction_version: Literal["1"]
    sources: list[dict]


class ExtractionState(ExtractionInput, total=False):
    status: str
    fields: list[dict]
    error: str | None


def source_chunks(sources: list[Source]):
    """Stay within the deployed 8K model context; prefer complete source lines."""
    for index, source in enumerate(sources):
        start = 0
        while start < len(source.text):
            end = min(start + 1000, len(source.text))
            if end < len(source.text):
                newline = source.text.rfind("\n", start + 500, end)
                if newline >= 0:
                    end = newline + 1
            yield {"source_index": index, "text": source.text[start:end]}
            if end == len(source.text):
                break
            # Overlap only when a very long line must be split. Never drop text.
            start = end if source.text[end - 1] == "\n" else end - 100


async def extract(state):
    model = None
    try:
        request = ExtractionRequest.model_validate(
            {
                key: state.get(key)
                for key in ("workflow_id", "extraction_version", "sources")
            }
        )
        settings = replace(
            OpenAICompatibleSettings.from_env(), max_attempts=1, timeout_seconds=100
        )
        model = OpenAICompatibleChatModel(settings)
        semaphore = asyncio.Semaphore(2)

        async def analyse_chunk(chunk):
            async with semaphore:
                source_text = request.sources[chunk["source_index"]].text
                context = chat_context(source_text)
                data = {**chunk, "chat_context": context} if context else chunk
                for attempt in range(2):
                    reminder = (
                        (
                            "\nPrevious draft incorrectly assigned a reply sender as a subject. "
                            "Reanalyse the body names and their nearby address/contact details; "
                            "do not use reply_sender_headers as case subjects."
                        )
                        if attempt
                        else ""
                    )
                    completion = await model.complete_structured(
                        [
                            {"role": "system", "content": PROMPT + reminder},
                            {
                                "role": "user",
                                "content": json.dumps([data], ensure_ascii=False),
                            },
                        ],
                        response_schema=Extraction.model_json_schema(),
                        schema_name="ax768_information_extraction",
                        max_tokens=3500,
                        temperature=0,
                    )
                    if completion.finish_reason != "stop":
                        raise ValueError("Incomplete model response")
                    partial = Extraction.model_validate_json(completion.text)
                    for item in partial.fields:
                        if (
                            item.source_index != chunk["source_index"]
                            or item.value not in chunk["text"]
                        ):
                            raise ValueError("Ungrounded chunk value")
                    if not assigns_sender_as_subject(partial.fields, source_text):
                        return partial.fields
                raise ValueError("Reply sender still assigned as subject")

        async with asyncio.timeout(100):
            parts = await asyncio.gather(
                *(analyse_chunk(chunk) for chunk in source_chunks(request.sources)),
                return_exceptions=True,
            )
        fields = {}
        for part in parts:
            if isinstance(part, BaseException):
                raise ModelRequestError(
                    "Source analysis failed", retryable=False
                ) from part
            for item in part:
                key = (item.source_index, item.label, item.value)
                if key in fields:
                    fields[key].uncertain |= item.uncertain
                else:
                    fields[key] = item
        result = Extraction(
            fields=include_subject_names(list(fields.values()), request.sources)
        )
        validate_grounding(result, request.sources)
        return {
            "status": "completed",
            "fields": result.model_dump()["fields"],
            "error": None,
        }
    except (ValueError, ModelRequestError, TimeoutError):
        # Never expose provider errors or return an old/partially validated draft.
        return {
            "status": "failed",
            "fields": [],
            "error": "Information extraction failed. Review the original text and try again.",
        }
    finally:
        if model is not None:
            await model.aclose()


def create_graph(*, extract_node=extract):
    builder = StateGraph(ExtractionState, input_schema=ExtractionInput)
    builder.add_node("extract", extract_node)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", END)
    return builder.compile()


graph = create_graph()
