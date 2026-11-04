"""Run a bounded AX768 task using the workspace's unified .env."""

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from workflows.ax768.cases import CASE_DESCRIPTIONS, case_action


def main(argv=None):
    parser = argparse.ArgumentParser(description="AX768 local Google Sheets agent")
    parser.add_argument(
        "--case",
        dest="case_id",
        choices=tuple(CASE_DESCRIPTIONS),
        help="Workflow case: "
        + "; ".join(f"{key}: {value}" for key, value in CASE_DESCRIPTIONS.items()),
    )
    parser.add_argument("message", help="Spreadsheet task in natural language")
    args = parser.parse_args(argv)
    try:
        case_action(args.case_id, args.message)
    except ValueError as exc:
        parser.error(str(exc))
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    from workflows.ax768.graph import graph

    result = asyncio.run(
        graph.ainvoke(
            {"message": args.message, "case_id": args.case_id}, {"recursion_limit": 32}
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
