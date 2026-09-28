"""JSON logging with explicit metadata allowlists and content-free exceptions."""

import json
import logging
from datetime import UTC, datetime


class JsonDiagnosticFormatter(logging.Formatter):
    """Keep approved scalar metadata; never serialize exception text or locals."""

    def __init__(self, fields: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.fields = fields

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in self.fields:
            value = getattr(record, field, None)
            if value is not None and isinstance(value, (str, int, float, bool)):
                data[field] = value
        if record.exc_info and record.exc_info[1] is not None:
            data["error_type"] = type(record.exc_info[1]).__name__
            cause = record.exc_info[1].__cause__
            if cause is not None:
                data["cause_type"] = type(cause).__name__
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
