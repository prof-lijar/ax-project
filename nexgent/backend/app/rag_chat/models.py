"""Public request contract for dedicated RAG Chat."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RagChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=100_000)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must be a non-empty string")
        return value
