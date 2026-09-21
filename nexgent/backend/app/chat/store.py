"""Transactional chat operations shared by the HTTP API and independent worker."""

import base64
import hashlib
import json
import os
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import sessionmaker

from app.chat.persistence import (
    Attachment,
    Conversation,
    Message,
    MessageAttachment,
    Run,
)
from app.identity.models import User, now
from app.identity.store import AccessError

ACTIVE = ("queued", "running")
TERMINAL = ("completed", "stopped", "failed", "interrupted")


def attachment_view(row):
    return {"id": row.id, "name": row.name, "size": row.size, "type": row.media_type}


def file_record(row):
    return {**attachment_view(row), "sha256": row.sha256, "normalized": row.normalized}


def encode_cursor(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def decode_cursor(value):
    try:
        if len(value) > 1024:
            raise ValueError()
        return json.loads(base64.urlsafe_b64decode(value))
    except (ValueError, TypeError):
        raise AccessError(422, "invalid_cursor") from None


class ChatStore:
    def __init__(self, engine, deployment=None):
        self.engine = engine
        self.deployment = deployment or os.getenv("AX_CHAT_DEPLOYMENT", "default")
        self.sessions = sessionmaker(engine, expire_on_commit=False)

    def ready(self):
        with self.sessions() as db:
            db.execute(select(Conversation.id).limit(1))

    def owned(self, db, owner, conversation_id, *, lock=False):
        query = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.deployment == self.deployment,
            Conversation.owner_id == owner,
            Conversation.deleted_at.is_(None),
        )
        row = db.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise AccessError(404, "not_found")
        return row

    def summary(self, db, row):
        run = db.scalar(
            select(Run).where(Run.conversation_id == row.id, Run.status.in_(ACTIVE))
        )
        return {
            "id": row.id,
            "title": row.title,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "active_run_id": run.id if run else None,
        }

    def conversations(self, owner, cursor=None, limit=30):
        with self.sessions() as db:
            query = select(Conversation).where(
                Conversation.owner_id == owner,
                Conversation.deployment == self.deployment,
                Conversation.deleted_at.is_(None),
            )
            if cursor:
                try:
                    stamp, ident = decode_cursor(cursor)
                    stamp = datetime.fromisoformat(stamp)
                    ident = str(UUID(ident))
                except (ValueError, TypeError):
                    raise AccessError(422, "invalid_cursor") from None
                query = query.where(
                    or_(
                        Conversation.updated_at < stamp,
                        and_(Conversation.updated_at == stamp, Conversation.id < ident),
                    )
                )
            rows = list(
                db.scalars(
                    query.order_by(
                        Conversation.updated_at.desc(), Conversation.id.desc()
                    ).limit(limit + 1)
                )
            )
            return {
                "items": [self.summary(db, r) for r in rows[:limit]],
                "next_cursor": encode_cursor(
                    [rows[limit - 1].updated_at.isoformat(), rows[limit - 1].id]
                )
                if len(rows) > limit
                else None,
            }

    def conversation(self, owner, ident):
        with self.sessions() as db:
            return self.summary(db, self.owned(db, owner, ident))

    def rename(self, owner, ident, title):
        with self.sessions.begin() as db:
            row = self.owned(db, owner, ident, lock=True)
            row.title = title
            return self.summary(db, row)

    def message_view(self, db, row):
        files = db.scalars(
            select(Attachment)
            .join(MessageAttachment)
            .where(MessageAttachment.message_id == row.id)
            .order_by(Attachment.id)
        )
        return {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "status": row.status,
            "position": row.position,
            "created_at": row.created_at.isoformat(),
            "attachments": [attachment_view(f) for f in files],
        }

    def messages(self, owner, ident, cursor=None, limit=50):
        with self.sessions() as db:
            self.owned(db, owner, ident)
            query = select(Message).where(Message.conversation_id == ident)
            if cursor:
                position = decode_cursor(cursor)
                if type(position) is not int or position < 1:
                    raise AccessError(422, "invalid_cursor")
                query = query.where(Message.position < position)
            rows = list(
                db.scalars(query.order_by(Message.position.desc()).limit(limit + 1))
            )
            page = rows[:limit]
            return {
                "items": [self.message_view(db, r) for r in reversed(page)],
                "next_cursor": encode_cursor(page[-1].position)
                if len(rows) > limit
                else None,
            }

    def attachments(self, owner, ident, cursor=None, limit=50):
        with self.sessions() as db:
            self.owned(db, owner, ident)
            query = select(Attachment).where(Attachment.conversation_id == ident)
            if cursor:
                value = decode_cursor(cursor)
                if not isinstance(value, str):
                    raise AccessError(422, "invalid_cursor")
                query = query.where(Attachment.id > value)
            rows = list(db.scalars(query.order_by(Attachment.id).limit(limit + 1)))
            return {
                "items": [attachment_view(r) for r in rows[:limit]],
                "next_cursor": encode_cursor(rows[limit - 1].id)
                if len(rows) > limit
                else None,
            }

    def attachment(self, owner, ident):
        with self.sessions() as db:
            row = db.get(Attachment, ident)
            if row is None:
                raise AccessError(404, "not_found")
            self.owned(db, owner, row.conversation_id)
            return file_record(row)

    def selected_files(self, owner, ident, ids):
        with self.sessions() as db:
            self.owned(db, owner, ident)
            rows = list(
                db.scalars(
                    select(Attachment).where(
                        Attachment.conversation_id == ident, Attachment.id.in_(ids)
                    )
                )
            )
            if len(rows) != len(set(ids)):
                raise AccessError(404, "not_found")
            return [file_record(r) for r in rows]

    @staticmethod
    def submission_view(run):
        return {
            "conversation_id": run.conversation_id,
            "user_message_id": run.user_message_id,
            "assistant_message_id": run.assistant_message_id,
            "run_id": run.id,
        }

    def submit(self, owner, ident, prompt, request_key, prepared, selected):
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "conversation": ident,
                    "prompt": prompt,
                    "uploads": [
                        {k: f[k] for k in ("name", "size", "sha256")} for f in prepared
                    ],
                    "selected": sorted(f["id"] for f in selected),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with self.sessions.begin() as db:
            # Serializes duplicate keys including first-message creation on different API workers.
            user = db.scalar(select(User).where(User.id == owner).with_for_update())
            if user is None or not user.is_active:
                raise AccessError(401, "authentication_required")
            previous = db.scalar(
                select(Run).where(
                    Run.owner_id == owner,
                    Run.request_key == request_key,
                    Run.deployment == self.deployment,
                )
            )
            if previous:
                self.owned(db, owner, previous.conversation_id)
                if previous.fingerprint != fingerprint:
                    raise AccessError(409, "idempotency_conflict")
                return self.submission_view(previous), False
            if ident:
                conversation = self.owned(db, owner, ident, lock=True)
            else:
                conversation = Conversation(
                    owner_id=owner,
                    deployment=self.deployment,
                    title=" ".join(prompt.split())[:48],
                )
                db.add(conversation)
                db.flush()
            if db.scalar(
                select(Run.id).where(
                    Run.conversation_id == conversation.id, Run.status.in_(ACTIVE)
                )
            ):
                raise AccessError(409, "chat_session_busy")
            # Recheck file membership under the same lock used by deletion.
            for file in selected:
                row = db.get(Attachment, file["id"])
                if row is None or row.conversation_id != conversation.id:
                    raise AccessError(404, "not_found")
            position = (
                db.scalar(
                    select(func.max(Message.position)).where(
                        Message.conversation_id == conversation.id
                    )
                )
                or 0
            )
            user_message = Message(
                conversation_id=conversation.id,
                position=position + 1,
                role="user",
                content=prompt,
            )
            assistant = Message(
                conversation_id=conversation.id,
                position=position + 2,
                role="assistant",
                status="waiting",
            )
            db.add_all([user_message, assistant])
            db.flush()
            for file in prepared:
                db.add(
                    Attachment(
                        id=file["id"],
                        conversation_id=conversation.id,
                        name=file["name"],
                        size=file["size"],
                        media_type=file["type"],
                        sha256=file["sha256"],
                        normalized=file["normalized"],
                    )
                )
            db.flush()
            db.add_all(
                [
                    MessageAttachment(message_id=user_message.id, attachment_id=f["id"])
                    for f in [*prepared, *selected]
                ]
            )
            run = Run(
                owner_id=owner,
                deployment=self.deployment,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                assistant_message_id=assistant.id,
                request_key=request_key,
                fingerprint=fingerprint,
            )
            db.add(run)
            conversation.updated_at = now()
            db.flush()
            return self.submission_view(run), True

    def run(self, owner, ident):
        with self.sessions() as db:
            run = db.get(Run, ident)
            if run is None or run.owner_id != owner:
                raise AccessError(404, "not_found")
            self.owned(db, owner, run.conversation_id)
            return {
                **self.submission_view(run),
                "status": run.status,
                "revision": run.revision,
                "cancel_requested": run.cancel_requested,
                "error_code": run.error_code,
                "message": self.message_view(
                    db, db.get(Message, run.assistant_message_id)
                ),
            }

    def cancel(self, owner, ident):
        with self.sessions.begin() as db:
            run = db.get(Run, ident)
            if run is None or run.owner_id != owner:
                raise AccessError(404, "not_found")
            self.owned(db, owner, run.conversation_id, lock=True)
            run = db.scalar(
                select(Run)
                .where(Run.id == ident)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if run.status in ACTIVE:
                run.cancel_requested = True
                if run.status == "queued":
                    self.finish(db, run, "stopped")

    def remove(self, owner, ident):
        with self.sessions.begin() as db:
            row = self.owned(db, owner, ident, lock=True)
            row.deleted_at = now()
            for run in db.scalars(
                select(Run)
                .where(Run.conversation_id == ident, Run.status.in_(ACTIVE))
                .with_for_update()
            ):
                run.cancel_requested = True
                if run.status == "queued":
                    self.finish(db, run, "stopped")

    @staticmethod
    def finish(db, run, status, error=None):
        run.status, run.error_code, run.finished_at = status, error, now()
        run.lease_until = None
        run.revision += 1
        message = db.get(Message, run.assistant_message_id)
        message.status = {"completed": "complete", "stopped": "stopped"}.get(
            status, "failed"
        )

    def claim(self):
        with self.sessions.begin() as db:
            run = db.scalar(
                select(Run)
                .where(Run.status == "queued", Run.deployment == self.deployment)
                .order_by(Run.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if run is None:
                return None
            run.status, run.lease_token, run.lease_until = (
                "running",
                str(uuid4()),
                now() + timedelta(seconds=60),
            )
            run.revision += 1
            return {
                "id": run.id,
                "token": run.lease_token,
                "conversation_id": run.conversation_id,
            }

    def input(self, ident):
        with self.sessions() as db:
            run = db.get(Run, ident)
            message = db.get(Message, run.user_message_id)
            previous = list(
                db.scalars(
                    select(Run)
                    .where(
                        Run.conversation_id == run.conversation_id,
                        Run.status == "completed",
                        Run.created_at < run.created_at,
                    )
                    .order_by(Run.created_at.desc())
                    .limit(20)
                )
            )
            history, size = [], 0
            for old in previous:
                user, assistant = (
                    db.get(Message, old.user_message_id),
                    db.get(Message, old.assistant_message_id),
                )
                size += len(user.content) + len(assistant.content)
                if size > 32000:
                    break
                history.insert(
                    0, {"user": user.content, "assistant": assistant.content}
                )
            files = list(
                db.scalars(
                    select(Attachment)
                    .join(MessageAttachment)
                    .where(MessageAttachment.message_id == message.id)
                )
            )
            return message.content, history, [file_record(f) for f in files]

    def heartbeat(self, ident, token):
        with self.sessions.begin() as db:
            run = db.scalar(
                select(Run)
                .where(Run.id == ident, Run.lease_until > now())
                .with_for_update()
            )
            if (
                run is None
                or run.status != "running"
                or run.lease_token != token
                or run.cancel_requested
            ):
                return False
            run.lease_until = now() + timedelta(seconds=60)
            return True

    def output(self, ident, token, content, status=None, error=None):
        with self.sessions.begin() as db:
            run = db.get(Run, ident)
            if run is None:
                return False
            conversation = db.scalar(
                select(Conversation)
                .where(Conversation.id == run.conversation_id)
                .with_for_update()
            )
            run = db.scalar(
                select(Run)
                .where(Run.id == ident, Run.lease_until > now())
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if run is None or run.status != "running" or run.lease_token != token:
                return False
            if conversation.deleted_at or run.cancel_requested:
                if not conversation.deleted_at:
                    db.get(Message, run.assistant_message_id).content = content
                self.finish(db, run, "stopped")
                return False
            message = db.get(Message, run.assistant_message_id)
            message.content, message.status = content, "streaming"
            run.revision += 1
            if status:
                self.finish(db, run, status, error)
                conversation.updated_at = now()
            return True

    def recover(self):
        with self.sessions.begin() as db:
            for run in db.scalars(
                select(Run)
                .where(
                    Run.status == "running",
                    Run.deployment == self.deployment,
                    Run.lease_until < now(),
                )
                .with_for_update(skip_locked=True)
            ):
                self.finish(db, run, "interrupted", "worker_interrupted")

    def garbage(self):
        with self.sessions() as db:
            ids = list(
                db.scalars(
                    select(Conversation.id)
                    .where(
                        Conversation.deleted_at.is_not(None),
                        Conversation.deployment == self.deployment,
                        ~select(Run.id)
                        .where(
                            Run.conversation_id == Conversation.id,
                            Run.status.in_(ACTIVE),
                        )
                        .exists(),
                    )
                    .limit(50)
                )
            )
            return [
                (
                    ident,
                    list(
                        db.scalars(
                            select(Attachment.id).where(
                                Attachment.conversation_id == ident
                            )
                        )
                    ),
                )
                for ident in ids
            ]

    def purge(self, ident):
        with self.sessions.begin() as db:
            row = db.get(Conversation, ident)
            if (
                row
                and row.deleted_at
                and not db.scalar(
                    select(Run.id).where(
                        Run.conversation_id == ident, Run.status.in_(ACTIVE)
                    )
                )
            ):
                # Explicit ordering also supports SQLite tests without relying on cascade setup.
                ids = select(Message.id).where(Message.conversation_id == ident)
                db.execute(
                    delete(MessageAttachment).where(
                        MessageAttachment.message_id.in_(ids)
                    )
                )
                for model in (Run, Attachment, Message):
                    db.execute(delete(model).where(model.conversation_id == ident))
                db.delete(row)

    def file_exists(self, ident):
        with self.sessions() as db:
            return db.get(Attachment, ident) is not None
