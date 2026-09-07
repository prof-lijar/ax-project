"""Environment-backed service composition for the weekly-report API."""

from ax_integrations import AsyncpgReadOnlyDatabase, PostgresSettings

from workflows.weekly_report.source import WeeklyReportSourceService


def build_default_service() -> tuple[
    AsyncpgReadOnlyDatabase, WeeklyReportSourceService
]:
    database = AsyncpgReadOnlyDatabase(PostgresSettings.from_env())
    return database, WeeklyReportSourceService(database)
