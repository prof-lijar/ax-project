#!/usr/bin/env python3
"""Small streaming chat client for an OpenAI-compatible HTTP endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_URL = "http://127.0.0.1:8000/v1/chat/completions"
DEFAULT_MODEL = "gemma-4-31b"
COMPLETIONS_PATH = "/chat/completions"


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without overwriting shell variables."""
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if separator and key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip("'\"")


def completion_url(url: str) -> str:
    """Accept either a full endpoint or an OpenAI-compatible base URL."""
    normalized = url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return normalized + COMPLETIONS_PATH
    return normalized + "/v1" + COMPLETIONS_PATH


def stream_completion(
    url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
) -> Iterator[str]:
    """Send one request and yield text deltas from an SSE response."""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    request = Request(
        completion_url(url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    with urlopen(request, timeout=600) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue

            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                return

            try:
                event = json.loads(data)
                choices = event.get("choices", [])
                delta = choices[0].get("delta", {}) if choices else {}
                content = delta.get("content")
            except (IndexError, TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Invalid streaming response: {data!r}") from exc

            if content:
                yield content


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("OPENAI_BASE_URL", DEFAULT_URL))
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--temperature", type=float, default=0.7)
    return parser.parse_args()


def main() -> int:
    load_dotenv(Path(__file__).with_name(".env"))
    args = parse_args()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Set OPENAI_API_KEY before starting the chat.", file=sys.stderr)
        return 2

    messages: list[dict[str, str]] = []
    print("Streaming chat started. Type 'exit' or press Ctrl-D to quit.")

    while True:
        try:
            prompt = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not prompt:
            continue
        if prompt.lower() in {"exit", "quit"}:
            return 0

        messages.append({"role": "user", "content": prompt})
        print("Assistant: ", end="", flush=True)
        answer: list[str] = []
        try:
            for chunk in stream_completion(
                args.url,
                api_key,
                args.model,
                messages,
                args.max_tokens,
                args.temperature,
            ):
                print(chunk, end="", flush=True)
                answer.append(chunk)
            print()
        except HTTPError as exc:
            print(
                f"\nRequest failed ({exc.code}) at {completion_url(args.url)}: "
                f"{exc.read().decode('utf-8', 'replace')}",
                file=sys.stderr,
            )
            messages.pop()
            continue
        except (URLError, TimeoutError, RuntimeError) as exc:
            print(f"\nRequest failed: {exc}", file=sys.stderr)
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": "".join(answer)})


if __name__ == "__main__":
    raise SystemExit(main())
