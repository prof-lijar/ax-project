import time
from datetime import datetime


def task_a():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Task A START")
    time.sleep(3)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Task A END")


def task_b():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Task B START")
    time.sleep(3)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Task B END")


def task_c():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Task C START")
    time.sleep(3)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Task C END")
