import logging
import re

from app.core.settings import SettingsError, get_settings
from app.file_storage.schemas import validate_name
from app.file_storage.upload_tree import parse_tree
from app.identity.store import AccessError
from app.nextcloud.client import NextcloudClient, NextcloudError, PRIVATE_FILES_ROOT
from starlette.concurrency import run_in_threadpool


logger = logging.getLogger(__name__)
PRIVATE_ROOT = PRIVATE_FILES_ROOT


def get_storage_client():
    try:
        return NextcloudClient(get_settings(), files_root=PRIVATE_ROOT)
    except SettingsError as exc:
        raise AccessError(503, "file_storage_unavailable") from exc


async def upload(store, client, settings, owner, parent, files, tree=None):
    blob_ids = []
    try:
        paths, directories = parse_tree(tree, len(files))
        if (not files and not directories) or len(files) > settings.max_files:
            raise AccessError(413, "too_many_files")
        prepared, contents, total = [], [], 0
        for index, file in enumerate(files):
            try:
                name = validate_name(paths[index].split("/")[-1] if paths is not None else file.filename or "")
            except ValueError as exc:
                raise AccessError(422, "invalid_filename") from exc
            # Never trust the multipart Content-Length or read an unbounded file.
            budget = min(settings.max_file_bytes, settings.max_batch_bytes - total)
            content = await file.read(budget + 1)
            if len(content) > budget:
                raise AccessError(413, "upload_too_large")
            total += len(content)
            content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
            if len(content_type) > 255 or not re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", content_type):
                content_type = "application/octet-stream"
            prepared.append({"name": name, "size": len(content),
                             "content_type": content_type})
            contents.append(content)
        blob_ids = await run_in_threadpool(store.reserve, owner, parent, prepared)
        if files:
            await client.create_folder("")
            await client.create_folder(settings.deployment)
            await client.create_folder(f"{settings.deployment}/{owner}")
        for blob_id, content in zip(blob_ids, contents, strict=True):
            await client.upload_file(f"{settings.deployment}/{owner}/{blob_id}", content,
                                     "application/octet-stream")
        if paths is not None:
            return await run_in_threadpool(store.finish, owner, parent, prepared, blob_ids, paths, directories)
        return await run_in_threadpool(store.finish, owner, parent, prepared, blob_ids)
    except NextcloudError as exc:
        raise AccessError(502, "file_storage_upstream_error") from exc
    finally:
        for file in files:
            await file.close()
        if blob_ids:
            try:
                # Successful batches are already ready and are unaffected.
                await run_in_threadpool(store.abort, owner, blob_ids)
            except Exception:
                logger.warning("File storage cleanup deferred to maintenance")


async def cleanup(store, client, limit=100):
    candidates = await run_in_threadpool(store.cleanup_candidates, limit)
    removed, failed = 0, 0
    for blob in candidates:
        try:
            try:
                await client.delete(blob["path"])
            except NextcloudError as exc:
                if exc.status_code != 404:
                    raise
            await run_in_threadpool(store.cleanup_done, blob["id"])
            removed += 1
        except NextcloudError:
            failed += 1
            logger.warning("File storage deletion deferred; Nextcloud unavailable")
    return {"removed": removed, "failed": failed}
