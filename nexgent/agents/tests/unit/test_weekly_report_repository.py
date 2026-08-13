from datetime import date

import pytest

from workflows.weekly_report.models import UserActivityWindow
from workflows.weekly_report.nodes import load_mock_activity


class StaticRepository:
    def __init__(self, users: list[UserActivityWindow]) -> None:
        self.users = users

    async def load_activity(self, **kwargs: object) -> list[UserActivityWindow]:
        return self.users


@pytest.mark.asyncio
async def test_repository_duplicate_users_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = [
        UserActivityWindow(user_id="duplicate", display_name="가", records=[]),
        UserActivityWindow(user_id="duplicate", display_name="나", records=[]),
    ]
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_weekly_activity_repository",
        lambda: StaticRepository(users),
    )

    with pytest.raises(ValueError, match="duplicate users"):
        await load_mock_activity(
            {
                "week_start": date(2026, 8, 3).isoformat(),
                "timezone": "Asia/Seoul",
            }
        )


@pytest.mark.asyncio
async def test_repository_batch_limit_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = [
        UserActivityWindow(
            user_id=f"user-{index:03d}", display_name="사용자", records=[]
        )
        for index in range(101)
    ]
    monkeypatch.setattr(
        "workflows.weekly_report.nodes.get_weekly_activity_repository",
        lambda: StaticRepository(users),
    )

    with pytest.raises(ValueError, match="exceeds 100"):
        await load_mock_activity({"week_start": "2026-08-03", "timezone": "Asia/Seoul"})
