from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from app.scout_schedule_models import ScoutRunFailure, ScoutRunSuccess


class ScoutApiCallError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class ScoutRunFailedResponse(ScoutApiCallError):
    def __init__(self, run: ScoutRunFailure) -> None:
        super().__init__("scout_run_failed", "Scout completed with a failed status.")
        self.run = run


class ScoutApiClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 180.0,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.base_url = base_url.rstrip("/")
        if not self.base_url:
            raise ValueError("base_url must not be blank")
        self.timeout_seconds = timeout_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def run_scout(
        self,
        topic: str,
        keywords: list[str],
        additional_instructions: str | None = None,
    ) -> ScoutRunSuccess:
        request_json: dict[str, object] = {"topic": topic, "keywords": keywords}
        if additional_instructions is not None:
            normalized_instructions = additional_instructions.strip()
            if normalized_instructions:
                request_json["additional_instructions"] = normalized_instructions
        try:
            response = self._client.post(
                f"{self.base_url}/v1/scout/runs",
                json=request_json,
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException:
            raise ScoutApiCallError(
                "scout_timeout",
                "Scout did not respond before the configured timeout.",
            ) from None
        except httpx.HTTPError:
            raise ScoutApiCallError(
                "scout_unreachable",
                "Scout could not be reached.",
            ) from None

        payload = _safe_json(response)
        if response.status_code == 200:
            try:
                return ScoutRunSuccess.model_validate(payload)
            except ValidationError:
                raise ScoutApiCallError(
                    "invalid_scout_response",
                    "Scout returned an invalid success response.",
                ) from None

        if (
            response.status_code == 502
            and isinstance(payload, dict)
            and "run" in payload
        ):
            try:
                failed_run = ScoutRunFailure.model_validate(payload["run"])
            except ValidationError:
                raise ScoutApiCallError(
                    "invalid_scout_failure_response",
                    "Scout returned invalid failed-run metadata.",
                ) from None
            raise ScoutRunFailedResponse(failed_run)

        raise ScoutApiCallError(
            "scout_preflight_failed",
            f"Scout rejected the request before a run completed (HTTP {response.status_code}).",
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None
