import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agent import run_scheduling_request
from app.scheduler_service import CALCULATOR_WORKFLOW_JOB_ID, scheduler

EXPECTED = datetime(2026, 8, 27, 3, 28, tzinfo=ZoneInfo("Asia/Seoul"))

async def main():
    try:
        confirmation = await run_scheduling_request(
            "Run the calculator workflow on August 27, 2026 at 3:28 AM Korea time."
        )
        print(confirmation)

        job = scheduler.get_job(CALCULATOR_WORKFLOW_JOB_ID)
        if job is None:
            raise RuntimeError("Calculator workflow job was not registered")

        if job.next_run_time != EXPECTED:
            raise RuntimeError(
                f"Unexpected run time: {job.next_run_time}; expected {EXPECTED}"
            )

        print(f"REGISTERED JOB: {job.id}")
        print(f"NEXT RUN: {job.next_run_time}")
        print("Scheduler will remain running. Press Ctrl+C to stop it.")

        while True:
            await asyncio.sleep(60)

    finally:
        scheduler.shutdown(wait=True)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Scheduler stopped cleanly.")
