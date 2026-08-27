import queue
import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from tasks import task_a, task_b, task_c


TASKS = [
    ("Task A", task_a),
    ("Task B", task_b),
    ("Task C", task_c),
]

job_queue = queue.Queue()


def enqueue_task(task_name, task_func):
    print(f"[QUEUE] {task_name} added")
    job_queue.put((task_name, task_func))


def worker():
    while True:
        task_name, task_func = job_queue.get()

        try:
            print(f"[WORKER] {task_name} picked up")
            task_func()
        finally:
            job_queue.task_done()


# 1. Scheduling mode
print("Select scheduling mode:")
print("1. Interval")
print("2. Cron")

schedule_choice = input("Enter choice (1 or 2): ").strip()

if schedule_choice == "1":
    interval = int(input("Enter interval in seconds: "))
    trigger = IntervalTrigger(seconds=interval)
    schedule_description = f"every {interval} seconds"

elif schedule_choice == "2":
    cron_expression = input(
        "Enter cron expression (example: */5 * * * *): "
    ).strip()

    try:
        trigger = CronTrigger.from_crontab(cron_expression)
    except ValueError as exc:
        print(f"Invalid cron expression: {exc}")
        raise SystemExit(1)

    schedule_description = f"cron: {cron_expression}"

else:
    print("Invalid scheduling mode.")
    raise SystemExit(1)


# 2. Execution policy
print("\nSelect execution policy:")
print("1. Parallel")
print("2. Sequential")

execution_choice = input("Enter choice (1 or 2): ").strip()

if execution_choice not in {"1", "2"}:
    print("Invalid execution policy.")
    raise SystemExit(1)


scheduler = BackgroundScheduler()


# 3. Register jobs
if execution_choice == "1":

    for task_name, task_func in TASKS:
        scheduler.add_job(
            task_func,
            trigger,
            id=task_name,
            max_instances=1,
        )

    execution_description = "parallel"

else:

    worker_thread = threading.Thread(
        target=worker,
        daemon=True,
    )
    worker_thread.start()

    for task_name, task_func in TASKS:
        scheduler.add_job(
            enqueue_task,
            trigger,
            args=[task_name, task_func],
            id=task_name,
            max_instances=1,
        )

    execution_description = "sequential queue"


# 4. Start scheduler
scheduler.start()

print("\nScheduler started.")
print(f"Schedule: {schedule_description}")
print(f"Execution: {execution_description}")
print("Tasks: A, B, C")
print("Press Ctrl+C to stop.")


try:
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\nStopping scheduler...")

    scheduler.shutdown(wait=False)

    # For the PoC, do not wait forever for accumulated backlog.
    if execution_choice == "2":
        remaining = job_queue.qsize()
        print(f"Queued tasks remaining: {remaining}")

    print("Scheduler stopped.")
