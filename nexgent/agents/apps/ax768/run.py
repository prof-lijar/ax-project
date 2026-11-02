"""Run a bounded AX768 task using the workspace's unified .env."""

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser(description="AX768 local Google Sheets agent")
    parser.add_argument("message", help="Spreadsheet task in natural language")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    from workflows.ax768.graph import graph

    result = asyncio.run(
        graph.ainvoke({"message": args.message}, {"recursion_limit": 32})
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
