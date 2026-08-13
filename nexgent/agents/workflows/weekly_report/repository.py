"""Activity repository port and the workflow's mock implementation."""

from collections.abc import Sequence
from datetime import date, timedelta
from functools import lru_cache
from typing import Protocol

from .models import DailyActivity, UserActivityWindow


class WeeklyActivityRepository(Protocol):
    async def load_activity(
        self,
        *,
        week_start: date,
        timezone: str,
    ) -> Sequence[UserActivityWindow]: ...


class MockWeeklyActivityRepository:
    """Create a stable three-user scenario relative to the requested week."""

    async def load_activity(
        self,
        *,
        week_start: date,
        timezone: str,
    ) -> Sequence[UserActivityWindow]:
        del timezone
        previous_start = week_start - timedelta(days=7)
        return [
            _window(
                "user-001",
                "김민지",
                previous_start,
                previous=[
                    (2, 1, 240, 1, 0),
                    (2, 1, 240, 0, 0),
                    (2, 1, 240, 1, 0),
                    (2, 1, 240, 0, 1),
                    (2, 2, 240, 0, 0),
                    (0, 0, 0, 0, 0),
                    (0, 0, 0, 0, 0),
                ],
                current=[
                    (2, 2, 300, 0, 0),
                    (2, 2, 300, 0, 0),
                    (2, 2, 300, 1, 0),
                    (2, 1, 300, 0, 1),
                    (2, 2, 300, 0, 0),
                    (0, 0, 0, 0, 0),
                    (0, 0, 0, 0, 0),
                ],
            ),
            _window(
                "user-002",
                "박준호",
                previous_start,
                previous=[
                    (2, 2, 270, 0, 0),
                    (2, 2, 270, 0, 0),
                    (2, 1, 270, 1, 0),
                    (1, 1, 255, 0, 1),
                    (1, 1, 255, 0, 0),
                    (0, 0, 0, 0, 0),
                    (0, 0, 0, 0, 0),
                ],
                current=[
                    (3, 2, 240, 1, 0),
                    (3, 2, 240, 1, 0),
                    (3, 1, 240, 1, 0),
                    (3, 2, 240, 0, 1),
                    (0, 0, 0, 0, 0),
                    (0, 0, 0, 0, 0),
                    (0, 0, 0, 0, 0),
                ],
            ),
            _window(
                "user-003",
                "이서연",
                previous_start,
                previous=[(0, 0, 0, 0, 0)] * 7,
                current=[
                    (2, 2, 270, 0, 0),
                    (1, 1, 270, 0, 0),
                    (1, 1, 270, 0, 0),
                    (1, 1, 270, 0, 0),
                    (0, 0, 0, 0, 0),
                    (0, 0, 0, 0, 0),
                    (0, 0, 0, 0, 0),
                ],
            ),
        ]


DailyValues = tuple[int, int, int, int, int]


def _window(
    user_id: str,
    display_name: str,
    previous_start: date,
    *,
    previous: list[DailyValues],
    current: list[DailyValues],
) -> UserActivityWindow:
    values = previous + current
    records = [
        DailyActivity(
            activity_date=previous_start + timedelta(days=offset),
            assigned_tasks=item[0],
            completed_tasks=item[1],
            focus_minutes=item[2],
            blockers_opened=item[3],
            blockers_resolved=item[4],
        )
        for offset, item in enumerate(values)
    ]
    return UserActivityWindow(
        user_id=user_id,
        display_name=display_name,
        records=records,
    )


@lru_cache(maxsize=1)
def get_weekly_activity_repository() -> WeeklyActivityRepository:
    return MockWeeklyActivityRepository()
