"""Run `ansimk_weekly_reporter` and display its Korean Markdown reports."""

import argparse
import asyncio
import sys
from importlib import import_module
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

graph = import_module("workflows.weekly_report").graph

DEFAULT_MAX_CONCURRENCY = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week-start", required=True, help="Monday in YYYY-MM-DD form")
    parser.add_argument("--timezone", default="Asia/Seoul")
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    result = await graph.ainvoke(
        {"week_start": args.week_start, "timezone": args.timezone},
        config={"max_concurrency": DEFAULT_MAX_CONCURRENCY},
    )
    for report in result["reports"]:
        print(report["markdown"])
    if result["warnings"]:
        print("경고:")
        for warning in result["warnings"]:
            print(f"- {warning}")


if __name__ == "__main__":
    asyncio.run(run())
