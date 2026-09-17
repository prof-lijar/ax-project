"""Workflow-owned PostgreSQL inbox and stable archive paths."""

import uuid

import asyncpg
from ax_contracts.sumin import SuminTask


class Store:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def enqueue(self, tasks: list[SuminTask]) -> None:
        async with self.pool.acquire() as connection, connection.transaction():
            for task in tasks:
                await connection.execute(
                    "INSERT INTO agent.sumin_events(key,payload) VALUES($1,$2::jsonb) "
                    "ON CONFLICT(key) DO NOTHING",
                    task.key,
                    task.model_dump_json(),
                )

    async def claim(self):
        # A deadline of 300s is strictly shorter than this 360s lease.
        return await self.pool.fetchrow(
            """WITH candidate AS (
                SELECT key FROM agent.sumin_events
                WHERE (status='pending' AND available_at <= NOW())
                   OR (status='running' AND lease_until < NOW())
                ORDER BY created_at, key FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE agent.sumin_events e SET status='running', attempts=attempts+1,
                lease_token=$1, lease_until=NOW()+INTERVAL '360 seconds', updated_at=NOW()
            FROM candidate c WHERE e.key=c.key RETURNING e.*""",
            uuid.uuid4(),
        )

    async def finish(self, row, error: str | None = None) -> None:
        status = (
            "completed"
            if error is None
            else ("failed" if row["attempts"] >= 5 else "pending")
        )
        await self.pool.execute(
            """UPDATE agent.sumin_events SET status=$3, error_code=$4, lease_token=NULL,
               lease_until=NULL, available_at=NOW()+($5 * INTERVAL '1 second'), updated_at=NOW()
               WHERE key=$1 AND lease_token=$2 AND status='running'""",
            row["key"],
            row["lease_token"],
            status,
            error,
            min(300, 10 * 2 ** min(row["attempts"], 5)),
        )

    async def folder(self, team: str, channel: str, proposed: str) -> str:
        # A reused channel name must never merge two different channels' archives.
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "INSERT INTO agent.sumin_channels(team_id,channel_id,folder) VALUES($1,$2,$3) "
                "ON CONFLICT(team_id,channel_id) DO NOTHING",
                team,
                channel,
                proposed,
            )
            return await connection.fetchval(
                "SELECT folder FROM agent.sumin_channels WHERE team_id=$1 AND channel_id=$2",
                team,
                channel,
            )

    async def file_path(self, task: SuminTask, proposed: str) -> str:
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "INSERT INTO agent.sumin_files(team_id,channel_id,file_id,path) VALUES($1,$2,$3,$4) "
                "ON CONFLICT(team_id,channel_id,file_id) DO NOTHING",
                task.team_id,
                task.channel_id,
                task.file_id,
                proposed,
            )
            return await connection.fetchval(
                "SELECT path FROM agent.sumin_files WHERE team_id=$1 AND channel_id=$2 AND file_id=$3",
                task.team_id,
                task.channel_id,
                task.file_id,
            )

    async def save_context(self, task: SuminTask) -> None:
        await self.pool.execute(
            "INSERT INTO agent.sumin_contexts(team_id,channel_id,file_id,event_id,message_text) "
            "VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING",
            task.team_id,
            task.channel_id,
            task.file_id,
            task.event_id,
            task.text,
        )

    async def match_context(self, task: SuminTask, terms: list[str]) -> set[str]:
        rows = await self.pool.fetch(
            "SELECT DISTINCT file_id FROM agent.sumin_contexts WHERE team_id=$1 AND channel_id=$2 "
            "AND EXISTS (SELECT 1 FROM unnest($3::text[]) term "
            "WHERE strpos(lower(message_text), term)>0) LIMIT 5000",
            task.team_id,
            task.channel_id,
            terms,
        )
        return {row["file_id"] for row in rows}

    async def save_file_metadata(self, task: SuminTask, file: dict) -> None:
        created = file.get("created")
        if not isinstance(created, (int, float)) or not 0 < created < 4102444800:
            created = None
        await self.pool.execute(
            "UPDATE agent.sumin_files SET original_name=$4, uploaded_at=to_timestamp($5), "
            "uploader_id=$6 WHERE team_id=$1 AND channel_id=$2 AND file_id=$3",
            task.team_id,
            task.channel_id,
            task.file_id,
            (file.get("name") or file.get("title") or task.file_id)[:500],
            created,
            file.get("user") or task.user_id,
        )

    async def search_metadata(
        self, task: SuminTask, terms: list[str], offset: int
    ) -> list[dict]:
        rows = await self.pool.fetch(
            """SELECT f.file_id, split_part(f.path,'/',-1) AS archive_name,
                COALESCE(f.original_name,split_part(f.path,'/',-1)) AS filename,
                f.uploaded_at, f.uploader_id, e.first_seen_at, c.upload_context
            FROM agent.sumin_files f
            CROSS JOIN LATERAL (
                SELECT string_agg(message_text, E'\\n') AS upload_context FROM (
                    SELECT left(message_text,400) AS message_text
                    FROM agent.sumin_contexts
                    WHERE team_id=f.team_id AND channel_id=f.channel_id AND file_id=f.file_id
                    ORDER BY event_id LIMIT 3
                ) context_rows
            ) c
            LEFT JOIN LATERAL (
                SELECT min(created_at) AS first_seen_at FROM agent.sumin_events
                WHERE payload->>'team_id'=f.team_id AND payload->>'channel_id'=f.channel_id
                    AND payload->>'file_id'=f.file_id
            ) e ON true
            WHERE f.team_id=$1 AND f.channel_id=$2 AND c.upload_context IS NOT NULL
                AND (cardinality($3::text[])=0 OR EXISTS (
                    SELECT 1 FROM unnest($3::text[]) term
                    WHERE strpos(lower(COALESCE(f.original_name,f.path)),lower(term))>0
                        OR strpos(lower(c.upload_context),lower(term))>0
                ))
            ORDER BY COALESCE(f.uploaded_at,e.first_seen_at) DESC NULLS LAST, f.file_id
            LIMIT 21 OFFSET $4""",
            task.team_id,
            task.channel_id,
            terms,
            offset,
        )
        return [dict(row) for row in rows]
