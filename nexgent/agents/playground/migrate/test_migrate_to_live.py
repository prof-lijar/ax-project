import contextlib
import importlib.util
import io
import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).with_name("migrate-to-live.py")
spec = importlib.util.spec_from_file_location("risk_live_copy", PATH)
live = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = live
spec.loader.exec_module(live)


class LiveCopyConfigTests(unittest.TestCase):
    def environment(self):
        return {
            "LIVE_DEV_DB_HOST": "postgres.internal",
            "LIVE_DEV_DB_USER": "dev_user",
            "LIVE_DEV_DB_PASSWORD": "db-secret",
            "LIVE_DEV_SSH_HOST": "bastion.example",
            "LIVE_DEV_SSH_ID": "operator",
            "LIVE_DEV_SSH_PASSWORD": "ssh-secret",
            "TARGET_DB_USER": "unused-production-user",
        }

    def test_exact_cli_and_preview_default(self):
        self.assertTrue(
            live.parse_args(["--migrate-to-live", "-target", "dev"]).migrate_to_live
        )
        self.assertFalse(live.parse_args(["-target", "dev"]).migrate_to_live)
        self.assertFalse(live.parse_args(["-target", "prod"]).migrate_to_live)
        self.assertTrue(
            live.parse_args(["--migrate-to-live", "-target", "prod"]).migrate_to_live
        )
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            live.parse_args(["--migrate-to-live", "-target", "production"])

    def test_dev_settings_use_only_dev_keys_and_hide_secrets(self):
        with patch.dict(os.environ, self.environment(), clear=True):
            config = live.DevSettings.from_env()
        self.assertEqual(config.db_user, "dev_user")
        self.assertEqual(config.db_name, "ansimk")
        self.assertEqual(config.db_schema, "ansimk")
        self.assertEqual((config.db_port, config.ssh_port), (5432, 22))
        self.assertNotIn("secret", repr(config))
        command = live.ssh_command(config, 15499, 8)
        self.assertIn("127.0.0.1:15499:postgres.internal:5432", command)
        self.assertIn("operator@bastion.example", command)
        self.assertNotIn("ssh-secret", command)
        self.assertNotIn("db-secret", command)

    def test_prod_settings_are_isolated_and_require_tls_by_default(self):
        env = self.environment()
        env.update({
            key.replace("LIVE_DEV_", "LIVE_PROD_"): value
            for key, value in self.environment().items() if key.startswith("LIVE_DEV_")
        })
        env["LIVE_PROD_DB_USER"] = "prod_user"
        env["LIVE_PROD_DB_HOST"] = "production.internal"
        original = env.copy()
        settings = live.DevSettings.from_env(env, target="prod")
        self.assertEqual(settings.target, "prod")
        self.assertEqual(settings.db_user, "prod_user")
        self.assertEqual(settings.db_host, "production.internal")
        self.assertEqual(settings.db_ssl, "require")
        self.assertEqual(env, original)
        self.assertNotIn("secret", repr(settings))
        env["LIVE_PROD_DB_SSL"] = "verify-full"
        self.assertEqual(live.DevSettings.from_env(env, target="prod").db_ssl, "verify-full")
        del env["LIVE_PROD_DB_PASSWORD"]
        with self.assertRaisesRegex(live.MigrationError, "Missing LIVE_PROD_DB_PASSWORD"):
            live.DevSettings.from_env(env, target="prod")

    def test_prod_validation_names_production_setting(self):
        env = {key.replace("LIVE_DEV_", "LIVE_PROD_"): value
               for key, value in self.environment().items()}
        env["LIVE_PROD_DB_HOST"] = "-invalid"
        with self.assertRaisesRegex(live.MigrationError, "LIVE_PROD_DB_HOST"):
            live.DevSettings.from_env(env, target="prod")

    def test_related_env_overrides(self):
        env = {
            **self.environment(),
            "LIVE_DEV_DB_PORT": "5433",
            "LIVE_DEV_DB_NAME": "devdb",
            "LIVE_DEV_DB_SCHEMA": "ansimk_dev",
            "LIVE_DEV_DB_SSL": "disable",
            "LIVE_DEV_SSH_PORT": "2222",
        }
        with patch.dict(os.environ, env, clear=True):
            config = live.DevSettings.from_env()
        self.assertEqual(config.db_port, 5433)
        self.assertEqual(config.ssh_port, 2222)
        self.assertEqual(config.db_schema, "ansimk_dev")
        self.assertEqual(config.db_name, "devdb")
        self.assertEqual(config.db_ssl, "disable")

    def test_console_endpoint_url_is_normalized_for_postgresql(self):
        env = {
            **self.environment(),
            "LIVE_DEV_DB_HOST": "http://postgres.internal:5433/",
        }
        with patch.dict(os.environ, env, clear=True):
            config = live.DevSettings.from_env()
        self.assertEqual(config.db_host, "postgres.internal")
        self.assertEqual(config.db_port, 5433)
        with self.assertRaises(live.MigrationError):
            live.database_endpoint("http://user:secret@postgres.internal/private")

    def test_bad_settings_fail_without_revealing_values(self):
        for key, value in (
            ("LIVE_DEV_DB_HOST", "-invalid"),
            ("LIVE_DEV_DB_SCHEMA", "bad;sql"),
            ("LIVE_DEV_DB_PORT", "0"),
            ("LIVE_DEV_SSH_PASSWORD", "bad\nsecret"),
        ):
            with (
                self.subTest(key=key),
                patch.dict(os.environ, {**self.environment(), key: value}, clear=True),
            ):
                with self.assertRaises(live.MigrationError) as error:
                    live.DevSettings.from_env()
                self.assertNotIn(value, str(error.exception))


@unittest.skipUnless(
    os.environ.get("RUN_MIGRATION_SQL_TESTS") == "1", "Enable PostgreSQL fixture tests."
)
class LiveCopySQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg

        live.load_dotenv(live.ENV_FILE, override=False)
        dsn = live.source_database_dsn()
        self.source = await asyncpg.connect(dsn, timeout=15)
        try:
            self.target = await asyncpg.connect(dsn, timeout=15)
        except BaseException:
            await self.source.close()
            raise
        definition = """(
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, ward_id bigint NOT NULL,
            month varchar(7) NOT NULL, total_risk_count integer NOT NULL,
            risk_days integer[], total_danger_stable_count integer NOT NULL,
            danger_stable_days integer[], created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL, UNIQUE(ward_id,month)
        )"""
        await self.source.execute("CREATE TEMP TABLE live_source_fixture " + definition)
        await self.target.execute(
            "CREATE TEMP TABLE resources_ward_monthly_risk_count " + definition
        )
        await self.target.execute(
            "CREATE TEMP TABLE resources_ward(id bigint PRIMARY KEY)"
        )
        await self.target.execute("INSERT INTO pg_temp.resources_ward VALUES (1),(2)")
        self.stamp = datetime(2026, 10, 22, 1, tzinfo=UTC)
        self.rows = [
            (1, "2026.10", 2, [14, 20], 1, [14], self.stamp, self.stamp),
            (2, "2026.10", 0, [], 0, [], self.stamp, self.stamp),
            (1, "2026.09", 1, [30], 0, [], self.stamp, self.stamp),
        ]
        fields = ", ".join(live.COPY_FIELDS)
        params = ", ".join(f"${i}" for i in range(1, 9))
        await self.source.executemany(
            f"INSERT INTO pg_temp.live_source_fixture ({fields}) VALUES ({params})",
            self.rows,
        )
        self.patch = patch(
            "workflows.daily_risk_counts.live_copy.SOURCE_TABLE",
            "pg_temp.live_source_fixture",
        )
        self.patch.start()

    async def asyncTearDown(self):
        self.patch.stop()
        await self.target.close()
        await self.source.close()

    async def copy(self, write=False, month=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return await live.copy_rows(
                self.source,
                self.target,
                schema="pg_temp",
                write=write,
                batch_size=2,
                month=month,
            )

    async def test_scheduled_copy_only_replaces_selected_month(self):
        await self.copy(True)
        await self.target.execute(
            "UPDATE pg_temp.resources_ward_monthly_risk_count SET risk_days=ARRAY[1], total_risk_count=1 WHERE month='2026.09'"
        )
        result = await self.copy(True, month="2026.10")
        self.assertEqual(result["source_rows"], 2)
        self.assertEqual(result["written"], 0)
        self.assertEqual(
            await self.target.fetchval(
                "SELECT risk_days FROM pg_temp.resources_ward_monthly_risk_count WHERE month='2026.09'"
            ),
            [1],
        )

    async def test_preview_rolls_back_and_copy_is_idempotent_with_exact_values(self):
        result = await self.copy()
        self.assertEqual((result["source_rows"], result["inserts"]), (3, 3))
        self.assertEqual(
            await self.target.fetchval(
                "SELECT count(*) FROM pg_temp.resources_ward_monthly_risk_count"
            ),
            0,
        )
        self.assertEqual((await self.copy(True))["written"], 3)
        copied = await self.target.fetch(
            "SELECT "
            + ", ".join(live.COPY_FIELDS)
            + " FROM pg_temp.resources_ward_monthly_risk_count ORDER BY ward_id,month"
        )
        self.assertEqual(
            [tuple(r) for r in copied], sorted(self.rows, key=lambda r: (r[0], r[1]))
        )
        original = await self.target.fetchrow(
            "SELECT * FROM pg_temp.resources_ward_monthly_risk_count WHERE ward_id=1 AND month='2026.10'"
        )
        await self.target.execute(
            "UPDATE pg_temp.resources_ward_monthly_risk_count SET danger_stable_days=ARRAY[20] WHERE ward_id=1 AND month='2026.10'"
        )
        self.assertEqual((await self.copy(True))["updates"], 1)
        fixed = await self.target.fetchrow(
            "SELECT * FROM pg_temp.resources_ward_monthly_risk_count WHERE ward_id=1 AND month='2026.10'"
        )
        self.assertEqual(fixed["id"], original["id"])
        self.assertEqual(fixed["danger_stable_days"], [14])
        self.assertEqual((await self.copy(True))["written"], 0)

    async def test_missing_parent_rows_are_skipped_in_preview_and_apply(self):
        # Ward 1 owns two months: both must be excluded together.
        await self.target.execute("DELETE FROM pg_temp.resources_ward WHERE id=1")
        preview = await self.copy()
        self.assertEqual(preview["source_rows"], 3)
        self.assertEqual(preview["eligible_rows"], 1)
        self.assertEqual(preview["skipped_wards"], 1)
        self.assertEqual(preview["skipped_rows"], 2)
        self.assertEqual(preview["inserts"], 1)
        self.assertEqual(
            await self.target.fetchval(
                "SELECT count(*) FROM pg_temp.resources_ward_monthly_risk_count"
            ),
            0,
        )
        copied = await self.copy(True)
        self.assertEqual(copied["written"], 1)
        self.assertEqual(
            await self.target.fetchval(
                "SELECT ward_id FROM pg_temp.resources_ward_monthly_risk_count"
            ),
            2,
        )
        repeated = await self.copy(True)
        self.assertEqual(repeated["written"], 0)
        self.assertEqual(repeated["unchanged"], 1)
        self.assertEqual(repeated["skipped_rows"], 2)

    async def test_all_missing_parents_produce_no_destination_writes(self):
        await self.target.execute("DELETE FROM pg_temp.resources_ward")
        result = await self.copy(True)
        self.assertEqual(result["source_rows"], 3)
        self.assertEqual(result["eligible_rows"], 0)
        self.assertEqual(result["skipped_wards"], 2)
        self.assertEqual(result["skipped_rows"], 3)
        self.assertEqual(result["written"], 0)
        self.assertEqual(result["unchanged"], 0)
        self.assertEqual(
            await self.target.fetchval(
                "SELECT count(*) FROM pg_temp.resources_ward_monthly_risk_count"
            ),
            0,
        )

    async def test_invalid_source_array_aborts_all_destination_writes(self):
        await self.source.execute(
            "UPDATE pg_temp.live_source_fixture SET danger_stable_days=ARRAY[13] WHERE ward_id=1 AND month='2026.10'"
        )
        with self.assertRaisesRegex(live.MigrationError, "invalid"):
            await self.copy(True)
        self.assertEqual(
            await self.target.fetchval(
                "SELECT count(*) FROM pg_temp.resources_ward_monthly_risk_count"
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
