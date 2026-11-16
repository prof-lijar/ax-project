"""Admin boundary for workflow-specific, read-only information extraction."""
from typing import Literal
from uuid import UUID, uuid5

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.chat.config import get_chat_settings
from app.identity.router import require_admin

router = APIRouter(prefix="/api/ax768/workflow", tags=["ax768"], dependencies=[Depends(require_admin)])
GRAPH = "ax768_information_extraction"
ASSISTANT_ID = str(uuid5(UUID("6ba7b821-9dad-11d1-80b4-00c04fd430c8"), GRAPH))


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=8000)


class ExtractionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workflow_id: Literal["information_update"]
    sources: list[Source] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def nonblank(self):
        if any(not source.text.strip() for source in self.sources):
            raise ValueError("Empty source")
        return self


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    label: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=8000)
    source_index: int = Field(ge=0, le=5)
    uncertain: bool


def normalize(payload, sources):
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise ValueError("Extraction failed")
    fields = payload.get("fields")
    if not isinstance(fields, list) or len(fields) > 200:
        raise ValueError("Invalid fields")
    result = [ExtractedField.model_validate(item) for item in fields]
    for item in result:
        if (not item.label.strip() or not item.value.strip() or item.source_index >= len(sources)
                or item.value not in sources[item.source_index].text):
            raise ValueError("Ungrounded extraction")
    if sum(len(item.label) + len(item.value) for item in result) > 56000:
        raise ValueError("Oversized extraction")
    return [item.model_dump() for item in result]


@router.post("/extract")
async def extract(body: ExtractionInput):
    url = get_chat_settings().agent_server_url
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(110, connect=5, pool=5), follow_redirects=False) as client:
            schema_response = await client.get(f"{url}/assistants/{ASSISTANT_ID}/schemas")
            if schema_response.status_code == 404:
                raise HTTPException(409, detail="Restart Agent Server to enable information extraction.")
            schema_response.raise_for_status()
            schema = schema_response.json()
            if schema.get("input_schema", {}).get("properties", {}).get("extraction_version", {}).get("const") != "1":
                raise HTTPException(409, detail="Restart Agent Server to enable information extraction.")
            response = await client.post(f"{url}/runs/wait", json={
                "assistant_id": GRAPH,
                "input": {**body.model_dump(), "extraction_version": "1"},
                "on_completion": "delete", "on_disconnect": "cancel",
                "config": {"recursion_limit": 4},
            })
            response.raise_for_status()
            if len(response.content) > 1_000_000:
                raise ValueError("Oversized extraction response")
            fields = normalize(response.json(), body.sources)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise HTTPException(502, detail="Information extraction failed. Review the original text and try again.") from None
    return {"workflow_id": body.workflow_id, "extraction_version": "1", "fields": fields}
