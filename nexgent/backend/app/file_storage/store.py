from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import re
from pathlib import PurePosixPath

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.file_storage.persistence import Blob, Entry
from app.file_storage.schemas import validate_name
from app.identity.models import User, new_id, now
from app.identity.store import AccessError


MAX_TREE_ENTRIES = 10000


def public(entry):
    values = {key: getattr(entry, key) for key in (
        "id", "parent_id", "name", "kind", "size", "content_type",
        "created_at", "updated_at", "deleted_at",
    )}
    # SQLite drops offsets and PostgreSQL uses its session timezone on reads.
    for key, value in values.items():
        if isinstance(value, datetime):
            values[key] = (value.replace(tzinfo=timezone.utc) if value.tzinfo is None
                           else value.astimezone(timezone.utc))
    return values


class StorageStore:
    def __init__(self, engine, deployment="default"):
        self.engine, self.deployment = engine, deployment
        self.sessions = sessionmaker(engine, expire_on_commit=False)

    def ready(self):
        with self.sessions() as db:
            db.execute(select(Entry.id).limit(1))
            db.execute(select(Blob.id).limit(1))

    def scope(self, model, owner):
        return model.deployment == self.deployment, model.owner_id == owner

    @contextmanager
    def mutation(self, owner):
        try:
            with self.sessions.begin() as db:
                # A short database-only lock serializes tree changes across API workers.
                # No Nextcloud request is made while this transaction is open.
                if db.scalar(select(User.id).where(User.id == owner).with_for_update()) is None:
                    raise AccessError(404, "not_found")
                yield db
        except IntegrityError as exc:
            raise AccessError(409, "name_or_reference_conflict") from exc

    def entry(self, db, owner, ident, *, deleted=False):
        entry = db.scalar(select(Entry).where(*self.scope(Entry, owner), Entry.id == ident))
        if entry is None or (entry.deleted_at is not None) != deleted:
            raise AccessError(404, "not_found")
        return entry

    def parent(self, db, owner, ident):
        if ident is not None:
            parent = self.entry(db, owner, ident)
            if parent.kind != "folder":
                raise AccessError(409, "parent_is_not_folder")

    def unique_name(self, db, owner, parent, name, *, kind="file", excluding=None):
        name = validate_name(name)
        query = select(Entry.name).where(*self.scope(Entry, owner), Entry.parent_id == parent,
                                        Entry.deleted_at.is_(None))
        if excluding:
            query = query.where(Entry.id != excluding)
        occupied = set(db.scalars(query))
        if name not in occupied:
            return name
        extension = PurePosixPath(name).suffix if kind == "file" else ""
        stem = name[:-len(extension)] if extension else name
        # A duplicate of report(1).pdf becomes report(2).pdf, not report(1)(1).pdf.
        stem = re.sub(r"\([1-9][0-9]*\)$", "", stem) or stem
        for number in range(1, len(occupied) + 2):
            marker = f"({number})"
            budget = 255 - len(marker)
            suffix = extension.encode("utf-8")[:budget - 1].decode("utf-8", errors="ignore")
            prefix = stem.encode("utf-8")[:budget - len(suffix.encode("utf-8"))].decode("utf-8", errors="ignore")
            candidate = f"{prefix}{marker}{suffix}"
            if candidate not in occupied:
                return candidate
        raise AssertionError("A free numbered name must exist")

    def tree(self, db, owner, root):
        descendants = select(Entry.id).where(*self.scope(Entry, owner), Entry.id == root).cte(recursive=True)
        descendants = descendants.union_all(
            select(Entry.id).join(descendants, Entry.parent_id == descendants.c.id)
            .where(*self.scope(Entry, owner))
        )
        entries = list(db.scalars(select(Entry).where(Entry.id.in_(select(descendants.c.id)))
                                  .limit(MAX_TREE_ENTRIES + 1)))
        if len(entries) > MAX_TREE_ENTRIES:
            raise AccessError(413, "folder_operation_too_large")
        return entries

    def list(self, owner, parent=None, *, query=None, trash=False, limit=100, offset=0):
        with self.sessions() as db:
            statement = select(Entry).where(*self.scope(Entry, owner))
            if trash:
                statement = statement.where(Entry.trash_root_id == Entry.id)
            else:
                self.parent(db, owner, parent)
                statement = statement.where(Entry.deleted_at.is_(None))
                if query is None:
                    statement = statement.where(Entry.parent_id == parent)
            if query is not None:
                # Search text is literal, including SQL wildcard characters.
                escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                statement = statement.where(Entry.name.ilike(f"%{escaped}%", escape="\\"))
            count = db.scalar(select(func.count()).select_from(statement.subquery()))
            entries = db.scalars(statement.order_by(Entry.kind.desc(), func.lower(Entry.name), Entry.id)
                                 .offset(offset).limit(limit))
            return {"items": [public(entry) for entry in entries], "total": count,
                    "limit": limit, "offset": offset}

    def detail(self, owner, ident):
        with self.sessions() as db:
            entry = self.entry(db, owner, ident)
            breadcrumbs, parent = [], entry.parent_id
            while parent:
                item = self.entry(db, owner, parent)
                breadcrumbs.append({"id": item.id, "name": item.name})
                parent = item.parent_id
            return {**public(entry), "breadcrumbs": list(reversed(breadcrumbs))}

    def folder(self, owner, name, parent=None):
        with self.mutation(owner) as db:
            self.parent(db, owner, parent)
            name = self.unique_name(db, owner, parent, name, kind="folder")
            entry = Entry(deployment=self.deployment, owner_id=owner, name=name, parent_id=parent, kind="folder")
            db.add(entry)
            db.flush()
            return public(entry)

    def relocate(self, owner, ident, *, name=None, parent=None, move=False):
        with self.mutation(owner) as db:
            entry = self.entry(db, owner, ident)
            target = parent if move else entry.parent_id
            self.parent(db, owner, target)
            ancestor = target
            while ancestor:
                if ancestor == ident:
                    raise AccessError(409, "folder_cycle")
                ancestor = self.entry(db, owner, ancestor).parent_id
            new_name = validate_name(name) if name is not None else entry.name
            new_name = self.unique_name(db, owner, target, new_name, kind=entry.kind, excluding=ident)
            entry.parent_id, entry.name, entry.updated_at = target, new_name, now()
            db.flush()
            return public(entry)

    def copy(self, owner, ident, parent=None, name=None):
        with self.mutation(owner) as db:
            source = self.entry(db, owner, ident)
            self.parent(db, owner, parent)
            entries = [item for item in self.tree(db, owner, ident) if item.deleted_at is None]
            # Prevent surprising recursively nested copies, as with a normal filesystem.
            if parent in {entry.id for entry in entries}:
                raise AccessError(409, "folder_cycle")
            name = validate_name(name) if name is not None else source.name
            name = self.unique_name(db, owner, parent, name, kind=source.kind)
            ids = {entry.id: new_id() for entry in entries}
            copied = None
            for entry in entries:
                copy = Entry(id=ids[entry.id], deployment=self.deployment, owner_id=owner,
                             parent_id=parent if entry.id == ident else ids[entry.parent_id],
                             name=name if entry.id == ident else entry.name,
                             kind=entry.kind, blob_id=entry.blob_id, size=entry.size,
                             content_type=entry.content_type)
                db.add(copy)
                if entry.id == ident:
                    copied = copy
            db.flush()
            return public(copied)

    def trash(self, owner, ident):
        with self.mutation(owner) as db:
            self.entry(db, owner, ident)
            timestamp = now()
            for entry in self.tree(db, owner, ident):
                if entry.deleted_at is None:
                    entry.deleted_at = entry.updated_at = timestamp
                    entry.trash_root_id = ident

    def restore(self, owner, ident, values):
        with self.mutation(owner) as db:
            entry = self.entry(db, owner, ident, deleted=True)
            if entry.trash_root_id != entry.id:
                raise AccessError(409, "restore_trash_root_first")
            parent = values.get("parent_id", entry.parent_id)
            self.parent(db, owner, parent)
            name = validate_name(values["name"]) if values.get("name") is not None else entry.name
            name = self.unique_name(db, owner, parent, name, kind=entry.kind)
            entries = list(db.scalars(select(Entry).where(*self.scope(Entry, owner), Entry.trash_root_id == ident)))
            entry.parent_id, entry.name = parent, name
            for item in entries:
                item.deleted_at = item.trash_root_id = None
                item.updated_at = now()
            db.flush()
            return public(entry)

    def purge(self, owner, ident):
        with self.mutation(owner) as db:
            entry = self.entry(db, owner, ident, deleted=True)
            if entry.trash_root_id != ident:
                raise AccessError(409, "purge_trash_root_first")
            tree = self.tree(db, owner, ident)
            entries = [item for item in tree if item.trash_root_id == ident]
            deleted_ids = {item.id for item in entries}
            # Items trashed independently remain recoverable when their original
            # parent is purged. Their restore destination becomes the user's root.
            for item in tree:
                if item.id not in deleted_ids and item.parent_id in deleted_ids:
                    item.parent_id = None
            db.flush()
            blob_ids = {item.blob_id for item in entries if item.blob_id}
            db.execute(delete(Entry).where(Entry.id.in_(deleted_ids)))
            for blob_id in blob_ids:
                if db.scalar(select(Entry.id).where(Entry.blob_id == blob_id).limit(1)) is None:
                    db.get(Blob, blob_id).state = "pending_delete"

    def reserve(self, owner, parent, files):
        with self.mutation(owner) as db:
            self.parent(db, owner, parent)
            for file in files:
                validate_name(file["name"])
            ids = []
            for file in files:
                blob = Blob(id=new_id(), deployment=self.deployment, owner_id=owner, size=file["size"])
                db.add(blob)
                ids.append(blob.id)
            return ids

    def finish(self, owner, parent, files, blob_ids, paths=None, directories=()):
        with self.mutation(owner) as db:
            self.parent(db, owner, parent)
            result = []
            folder_ids = {"": parent}
            # Every imported folder is new; conflicts rename it as a unit, never
            # merge its contents into an existing tree. Publish everything atomically.
            for path in directories:
                ancestor, _, name = path.rpartition('/')
                target = folder_ids[ancestor]
                entry = Entry(deployment=self.deployment, owner_id=owner, parent_id=target,
                              name=self.unique_name(db, owner, target, name, kind="folder"), kind="folder")
                db.add(entry)
                db.flush()
                folder_ids[path] = entry.id
                result.append(public(entry))
            for index, (file, blob_id) in enumerate(zip(files, blob_ids, strict=True)):
                target = folder_ids[paths[index].rpartition('/')[0]] if paths is not None else parent
                # Resolve names at commit time, after remote upload: another worker
                # may have created the requested name while Nextcloud was busy.
                named_file = {**file, "name": self.unique_name(db, owner, target, file["name"])}
                blob = db.scalar(select(Blob).where(*self.scope(Blob, owner), Blob.id == blob_id,
                                                  Blob.state == "uploading").with_for_update())
                if blob is None:
                    raise AccessError(409, "upload_expired")
                blob.state = "ready"
                entry = Entry(deployment=self.deployment, owner_id=owner, parent_id=target,
                              blob_id=blob.id, kind="file", **named_file)
                db.add(entry)
                db.flush()
                result.append(public(entry))
            return result

    def abort(self, owner, blob_ids):
        with self.mutation(owner) as db:
            for blob in db.scalars(select(Blob).where(*self.scope(Blob, owner), Blob.id.in_(blob_ids),
                                                    Blob.state == "uploading")):
                # If a commit succeeded but its acknowledgement was lost, ready blobs
                # remain referenced and must never be deleted by request compensation.
                blob.state = "pending_delete"

    def download(self, owner, ident):
        with self.sessions() as db:
            entry = self.entry(db, owner, ident)
            if entry.kind != "file":
                raise AccessError(409, "not_a_file")
            return public(entry), f"{self.deployment}/{owner}/{entry.blob_id}"

    def cleanup_candidates(self, limit=100):
        with self.sessions.begin() as db:
            # Upload requests have bounded I/O timeouts. A day also leaves ample
            # time for normal batches to finish before abandoned reservations expire.
            stale = now() - timedelta(days=1)
            candidates = list(db.scalars(select(Blob).where(
                Blob.deployment == self.deployment,
                (Blob.state == "pending_delete") | ((Blob.state == "uploading") & (Blob.created_at < stale)),
            ).order_by(Blob.created_at, Blob.id).limit(limit).with_for_update()))
            result = []
            for blob in candidates:
                blob.state = "pending_delete"
                result.append({"id": blob.id, "path": f"{self.deployment}/{blob.owner_id}/{blob.id}"})
            return result

    def cleanup_done(self, ident):
        with self.sessions.begin() as db:
            db.execute(delete(Blob).where(Blob.id == ident, Blob.deployment == self.deployment,
                                         Blob.state == "pending_delete"))
