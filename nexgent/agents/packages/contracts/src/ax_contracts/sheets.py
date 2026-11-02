"""Validated, capability-limited spreadsheet actions; no arbitrary API requests."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReadCells(Action):
    tool: Literal["read_cells"]
    range: str = Field(min_length=1, max_length=256)


class WriteCells(Action):
    tool: Literal["write_cells", "append_rows"]
    range: str = Field(min_length=1, max_length=256)
    values: list[list[str | int | float | bool]] = Field(min_length=1, max_length=200)
    input_mode: Literal["RAW", "USER_ENTERED"] = "RAW"

    @model_validator(mode="after")
    def bounded_values(self):
        if any(not row for row in self.values):
            raise ValueError("rows must not be empty")
        if sum(map(len, self.values)) > 2000:
            raise ValueError("at most 2000 cells per action")
        if len(str(self.values)) > 32000:
            raise ValueError("cell payload too large")
        return self


class ClearCells(Action):
    tool: Literal["clear_cells"]
    range: str = Field(min_length=1, max_length=256)


class AddTab(Action):
    tool: Literal["add_tab"]
    title: str = Field(min_length=1, max_length=100)


class RenameTab(Action):
    tool: Literal["rename_tab"]
    sheet_id: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=100)


class DeleteTab(Action):
    tool: Literal["delete_tab"]
    sheet_id: int = Field(ge=0)


class DeleteDimension(Action):
    tool: Literal["delete_rows", "delete_columns"]
    sheet_id: int = Field(ge=0)
    start_index: int = Field(ge=0)
    end_index: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered_indices(self):
        if not 0 < self.end_index - self.start_index <= 200:
            raise ValueError("delete span must contain 1 to 200 rows/columns")
        return self


class Finish(Action):
    tool: Literal["finish"]
    response: str = Field(min_length=1, max_length=8000)


SheetAction = Annotated[
    ReadCells
    | WriteCells
    | ClearCells
    | AddTab
    | RenameTab
    | DeleteTab
    | DeleteDimension
    | Finish,
    Field(discriminator="tool"),
]


class SheetDecision(Action):
    schema_version: Literal["1"] = "1"
    action: SheetAction
