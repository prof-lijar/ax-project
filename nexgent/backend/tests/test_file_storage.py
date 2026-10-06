import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.file_storage.persistence import Blob
from app.file_storage.service import cleanup, get_storage_client
from app.file_storage.store import StorageStore
from app.identity.models import now
from app.identity.store import AccessError
from app.nextcloud.client import DownloadedFile, NextcloudError
from test_chat_history import chat  # noqa: F401 -- migrated database and real browser sessions


BASE = "/api/file-storage"


class MemoryNextcloud:
    def __init__(self):
        self.files = {}
        self.calls = []
        self.fail_upload = False
        self.fail_delete = False

    async def create_folder(self, path):
        self.calls.append(("mkdir", path))
        return 201

    async def upload_file(self, path, content, content_type):
        self.calls.append(("upload", path))
        self.files[path] = content
        if self.fail_upload:
            raise NextcloudError("upstream private detail", 500)
        return 201

    async def download_file(self, path):
        self.calls.append(("download", path))
        return DownloadedFile(path, self.files[path], "text/html", path.split("/")[-1])

    async def delete(self, path):
        self.calls.append(("delete", path))
        if self.fail_delete:
            raise NextcloudError("unavailable", 503)
        if path not in self.files:
            raise NextcloudError("gone", 404)
        del self.files[path]
        return 204


@pytest.fixture
def storage(chat, monkeypatch):
    client, chat_store, users, login, _ = chat
    monkeypatch.setenv("FILE_STORAGE_DEPLOYMENT", "test")
    engine = chat_store.engine
    if engine.dialect.name == "sqlite":
        engine = engine.execution_options(schema_translate_map={"auth": None, "chat": None, "file_storage": None})
    store, cloud = StorageStore(engine, "test"), MemoryNextcloud()
    client.app.state.file_storage_store = store
    client.app.dependency_overrides[get_storage_client] = lambda: cloud
    headers = login()
    return client, store, cloud, users, login, headers


def folder(storage, name="Documents", parent=None):
    response = storage[0].post(BASE + "/folders", headers=storage[5], json={"name": name, "parent_id": parent})
    assert response.status_code == 201, response.text
    return response.json()


def upload(storage, name="report.txt", parent=None, content=b"report"):
    response = storage[0].post(BASE + "/files", headers=storage[5],
                               data={"parent_id": parent} if parent else {},
                               files=[("files", (name, content, "text/plain"))])
    assert response.status_code == 201, response.text
    return response.json()["items"][0]


def action(storage, entry, action_name, body=None):
    return storage[0].post(f"{BASE}/entries/{entry['id']}/{action_name}", headers=storage[5], json=body or {})


def trash(storage, entry):
    response = storage[0].delete(f"{BASE}/entries/{entry['id']}", headers=storage[5])
    assert response.status_code == 204, response.text


def purge(storage, entry):
    response = storage[0].delete(f"{BASE}/trash/{entry['id']}", headers=storage[5])
    assert response.status_code == 204, response.text


def test_browse_search_rename_move_and_download(storage):
    client, store, cloud, users, _, headers = storage
    parent = folder(storage)
    file = upload(storage, "보고서.txt", parent["id"])
    assert client.get(BASE + "/entries").json()["items"] == [parent]
    result = client.get(BASE + "/entries", params={"parent_id": parent["id"]}).json()
    assert result["items"] == [file]
    detail = client.get(f"{BASE}/entries/{file['id']}").json()
    assert detail["breadcrumbs"] == [{"id": parent["id"], "name": parent["name"]}]
    assert "blob_id" not in detail and "owner_id" not in detail
    response = client.patch(f"{BASE}/entries/{file['id']}", headers=headers, json={"name": "100%_done.txt"})
    assert response.status_code == 200
    assert client.get(BASE + "/entries", params={"q": "%_"}).json()["total"] == 1
    assert action(storage, file, "move", {"parent_id": None}).status_code == 200
    download = client.get(f"{BASE}/entries/{file['id']}/download")
    assert download.content == b"report"
    assert download.headers["content-type"] == "application/octet-stream"
    assert "100%25_done.txt" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"
    assert list(cloud.files)[0].startswith(f"test/{users[0]['id']}/")
    assert StorageStore(store.engine, "test").list(users[0]["id"])["total"] == 2
    assert StorageStore(store.engine, "other").list(users[0]["id"])["total"] == 0


def test_cross_user_operations_are_hidden_before_nextcloud(storage):
    client, _, cloud, _, login, _ = storage
    parent = folder(storage)
    file = upload(storage, parent=parent["id"])
    headers = login("bob")
    calls = len(cloud.calls)
    assert client.get(BASE + "/entries").json()["total"] == 0
    assert client.get(BASE + "/entries", params={"parent_id": parent["id"]}).status_code == 404
    for suffix in ("", "/download", "/preview"):
        assert client.get(f"{BASE}/entries/{file['id']}{suffix}").status_code == 404
    assert client.patch(f"{BASE}/entries/{file['id']}", headers=headers, json={"name": "stolen"}).status_code == 404
    for op in ("copy", "move"):
        assert client.post(f"{BASE}/entries/{file['id']}/{op}", headers=headers, json={}).status_code == 404
    assert client.delete(f"{BASE}/entries/{file['id']}", headers=headers).status_code == 404
    assert client.post(BASE + "/folders", headers=headers, json={"name": "x", "parent_id": parent["id"]}).status_code == 404
    assert client.post(BASE + "/files", headers=headers, data={"parent_id": parent["id"]},
                        files={"files": ("x", b"x")}).status_code == 404
    assert len(cloud.calls) == calls


def test_authentication_csrf_and_untrusted_owner(storage):
    client, _, _, _, _, headers = storage
    assert client.post(BASE + "/folders", json={"name": "x"}).status_code == 403
    assert client.post(BASE + "/folders", headers=headers, json={"name": "x", "owner_id": str(uuid4())}).status_code == 422
    client.cookies.clear()
    assert client.get(BASE + "/entries").status_code == 401
    assert client.post(BASE + "/files", files={"files": ("x", b"x")}).status_code == 401


@pytest.mark.parametrize("name", ["", " ", ".", "..", "../secret", "a/b", "a\\b", "line\nfeed", "a\x00b", "가" * 86])
def test_invalid_names(storage, name):
    client = storage[0]
    assert client.post(BASE + "/folders", headers=storage[5], json={"name": name}).status_code == 422


def test_conflicts_and_cycles(storage):
    client, _, cloud, _, _, headers = storage
    root = folder(storage)
    child = folder(storage, "child", root["id"])
    assert client.post(BASE + "/folders", headers=headers, json={"name": root["name"]}).json()["name"] == root["name"] + "(1)"
    for op in ("move", "copy"):
        assert action(storage, root, op, {"parent_id": child["id"]}).status_code == 409
        assert action(storage, root, op, {"parent_id": root["id"]}).status_code == 409
    file = upload(storage)
    assert client.post(BASE + "/folders", headers=headers, json={"name": "x", "parent_id": file["id"]}).status_code == 409
    duplicate = client.post(BASE + "/files", headers=headers, files={"files": (file["name"], b"other")})
    assert duplicate.status_code == 201
    assert duplicate.json()["items"][0]["name"] == "report(1).txt"
    assert action(storage, file, "copy").json()["name"] == "report(2).txt"
    assert client.get(f"{BASE}/entries/{file['id']}/download").content == b"report"


def test_recursive_copy_trash_restore_and_reference_safe_purge(storage):
    client, store, cloud, _, _, headers = storage
    parent = folder(storage)
    nested = folder(storage, "nested", parent["id"])
    file = upload(storage, parent=nested["id"])
    copied = action(storage, parent, "copy", {"name": "Copy"}).json()
    assert len(cloud.files) == 1
    assert client.get(BASE + "/entries", params={"q": "report"}).json()["total"] == 2
    trash(storage, parent)
    assert client.get(f"{BASE}/entries/{file['id']}/download").status_code == 404
    assert client.get(BASE + "/trash").json()["total"] == 1
    assert client.post(f"{BASE}/trash/{file['id']}/restore", headers=headers, json={}).status_code == 409
    restored = client.post(f"{BASE}/trash/{parent['id']}/restore", headers=headers, json={})
    assert restored.status_code == 200
    assert client.get(f"{BASE}/entries/{file['id']}/download").status_code == 200
    trash(storage, parent)
    purge(storage, parent)
    assert asyncio.run(cleanup(store, cloud))["removed"] == 0
    trash(storage, copied)
    purge(storage, copied)
    assert len(cloud.files) == 1  # durable cleanup, not remote I/O inside a DB transaction
    cloud.fail_delete = True
    assert asyncio.run(cleanup(store, cloud))["failed"] == 1
    cloud.fail_delete = False
    assert asyncio.run(cleanup(store, cloud))["removed"] == 1
    assert cloud.files == {}


def test_independently_trashed_descendant_can_restore_to_root(storage):
    client, _, _, _, _, headers = storage
    parent = folder(storage)
    file = upload(storage, parent=parent["id"])
    trash(storage, file)
    trash(storage, parent)
    assert client.post(f"{BASE}/trash/{file['id']}/restore", headers=headers, json={}).status_code == 404
    assert client.post(f"{BASE}/trash/{file['id']}/restore", headers=headers, json={"parent_id": None}).status_code == 200
    purge(storage, parent)
    assert client.get(f"{BASE}/entries/{file['id']}/download").status_code == 200


def test_restore_name_conflict_is_automatically_numbered(storage):
    client, _, _, _, _, headers = storage
    original = folder(storage)
    trash(storage, original)
    folder(storage)
    response = client.post(f"{BASE}/trash/{original['id']}/restore", headers=headers, json={})
    assert response.status_code == 200
    assert response.json()["name"] == original["name"] + "(1)"


def test_purge_parent_preserves_independent_trash_items(storage):
    client, store, cloud, _, _, headers = storage
    parent = folder(storage)
    file = upload(storage, parent=parent["id"])
    trash(storage, file)
    trash(storage, parent)
    purge(storage, parent)
    assert asyncio.run(cleanup(store, cloud))["removed"] == 0
    response = client.post(f"{BASE}/trash/{file['id']}/restore", headers=headers, json={})
    assert response.status_code == 200
    assert response.json()["parent_id"] is None
    assert client.get(f"{BASE}/entries/{file['id']}/download").status_code == 200


def test_batch_upload_is_atomic_and_limits_apply_before_nextcloud(storage, monkeypatch):
    client, _, cloud, _, _, headers = storage
    monkeypatch.setenv("FILE_STORAGE_MAX_FILE_BYTES", "4")
    monkeypatch.setenv("FILE_STORAGE_MAX_BATCH_BYTES", "6")
    for files in (
        [("files", ("a", b"12345"))],
        [("files", ("a", b"1234")), ("files", ("b", b"1234"))],
    ):
        assert client.post(BASE + "/files", headers=headers, files=files).status_code == 413
    assert cloud.calls == []
    duplicate = [("files", ("a", b"1")), ("files", ("a", b"2"))]
    response = client.post(BASE + "/files", headers=headers, files=duplicate)
    assert response.status_code == 201
    assert [item["name"] for item in response.json()["items"]] == ["a", "a(1)"]
    success = client.post(BASE + "/files", headers=headers,
                          files=[("files", ("a", b"1234")), ("files", ("b", b"12"))])
    assert success.status_code == 201
    assert [item["size"] for item in success.json()["items"]] == [4, 2]
    monkeypatch.setenv("FILE_STORAGE_MAX_FILES", "1")
    assert client.post(BASE + "/files", headers=headers, files=duplicate).status_code == 413


def test_upload_failure_sanitized_and_cleaned(storage):
    client, store, cloud, _, _, headers = storage
    cloud.fail_upload = True
    response = client.post(BASE + "/files", headers=headers, files={"files": ("a", b"data")})
    assert response.status_code == 502
    assert "private detail" not in response.text
    assert client.get(BASE + "/entries").json()["items"] == []
    assert len(cloud.files) == 1
    assert asyncio.run(cleanup(store, cloud))["removed"] == 1
    assert not cloud.files


def test_late_metadata_failure_and_ambiguous_commit(storage, monkeypatch):
    client, store, cloud, _, _, headers = storage
    original = store.finish

    def fail(*args):
        raise AccessError(409, "name_conflict")

    monkeypatch.setattr(store, "finish", fail)
    assert client.post(BASE + "/files", headers=headers, files={"files": ("a", b"data")}).status_code == 409
    assert asyncio.run(cleanup(store, cloud))["removed"] == 1

    def committed(*args):
        original(*args)
        raise AccessError(503, "lost_response")

    monkeypatch.setattr(store, "finish", committed)
    assert client.post(BASE + "/files", headers=headers, files={"files": ("a", b"data")}).status_code == 503
    assert client.get(BASE + "/entries").json()["total"] == 1
    assert asyncio.run(cleanup(store, cloud))["removed"] == 0
    assert len(cloud.files) == 1


def test_stale_reservations_and_missing_blob_cleanup(storage):
    _, store, cloud, users, _, _ = storage
    ids = store.reserve(users[0]["id"], None, [{"name": "old", "size": 1}])
    recent = store.reserve(users[0]["id"], None, [{"name": "recent", "size": 1}])
    with store.sessions.begin() as db:
        db.get(Blob, ids[0]).created_at = now() - timedelta(days=2)
    assert asyncio.run(cleanup(store, cloud))["removed"] == 1  # remote 404 is idempotent
    with store.sessions() as db:
        assert list(db.scalars(select(Blob.id))) == recent


def test_postgresql_concurrent_moves_cannot_create_cycle(storage):
    _, store, _, users, _, _ = storage
    if store.engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    left, right = folder(storage, "left"), folder(storage, "right")
    barrier = Barrier(2)

    def move(source, target):
        barrier.wait()
        try:
            store.relocate(users[0]["id"], source["id"], parent=target["id"], move=True)
            return "ok"
        except AccessError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(move, left, right), pool.submit(move, right, left)]
        assert sorted(result.result() for result in results) == ["folder_cycle", "ok"]


@pytest.mark.parametrize('name,content,kind,content_type', [
    ('notes.md', b'# Hello\n', 'text', 'text/markdown'),
    ('data.csv', b'A,B\n1,2', 'text', 'text/plain'),
    ('report.pdf', b'%PDF-1.7', 'pdf', 'application/pdf'),
    ('photo.png', b'png-content', 'image', 'image/png'),
])
def test_private_previews_use_logical_names(storage, name, content, kind, content_type):
    client = storage[0]
    entry = upload(storage, name, content=content)
    result = client.get(f"{BASE}/entries/{entry['id']}/preview")
    assert result.status_code == 200
    assert result.content == content
    assert result.headers['x-preview-kind'] == kind
    assert result.headers['content-type'].startswith(content_type)
    assert result.headers['content-disposition'].startswith('inline;')
    assert result.headers['x-content-type-options'] == 'nosniff'
    assert result.headers['cache-control'] == 'no-store'
    trash(storage, entry)
    assert client.get(f"{BASE}/entries/{entry['id']}/preview").status_code == 404


@pytest.mark.parametrize('extension', ['doc', 'docx', 'xls', 'xlsx', 'pptx', 'odt', 'ods'])
def test_office_previews_convert_named_content_not_blob_id(storage, monkeypatch, extension):
    from app.nextcloud.client import NextcloudClient, PreviewedFile
    seen = []

    def convert(downloaded):
        seen.append(downloaded)
        return PreviewedFile(downloaded.path, b'%PDF-converted', 'application/pdf', 'report.pdf', 'pdf')

    monkeypatch.setattr(NextcloudClient, '_convert_office_preview', staticmethod(convert))
    file = upload(storage, 'report.' + extension, content=b'office-original')
    result = storage[0].get(f"{BASE}/entries/{file['id']}/preview")
    assert result.status_code == 200
    assert result.content == b'%PDF-converted'
    assert seen[0].filename == 'report.' + extension
    assert seen[0].content == b'office-original'
    assert storage[0].get(f"{BASE}/entries/{file['id']}/download").content == b'office-original'


def test_preview_errors_are_safe_and_download_still_works(storage, monkeypatch):
    from app.nextcloud.client import NextcloudClient
    file = upload(storage, 'test.docx')
    for status, code in [(501, 'preview_converter_unavailable'), (504, 'preview_timeout'), (502, 'preview_failed')]:
        def fail(_):
            raise NextcloudError('private converter details', status)
        monkeypatch.setattr(NextcloudClient, '_convert_office_preview', staticmethod(fail))
        result = storage[0].get(f"{BASE}/entries/{file['id']}/preview")
        assert result.status_code == status
        assert result.json() == {'error': {'code': code}}
    assert storage[0].get(f"{BASE}/entries/{file['id']}/download").status_code == 200
    archive = upload(storage, 'archive.zip', content=b'\xff\xfe')
    result = storage[0].get(f"{BASE}/entries/{archive['id']}/preview")
    assert result.status_code == 415


@pytest.mark.parametrize('name, expected', [
    ('report.pdf', 'report(1).pdf'), ('report(1).pdf', 'report(2).pdf'),
    ('README', 'README(1)'), ('.env', '.env(1)'),
    ('archive.tar.gz', 'archive.tar(1).gz'), ('보고서.xlsx', '보고서(1).xlsx'),
    ('가' * 83 + '.txt', '가' * 82 + '(1).txt'),
])
def test_numbered_names_preserve_extensions_and_utf8_limits(storage, name, expected):
    original = upload(storage, name)
    duplicate = upload(storage, name, content=b'new bytes')
    assert duplicate['name'] == expected
    assert len(duplicate['name'].encode('utf-8')) <= 255
    assert storage[0].get(f"{BASE}/entries/{original['id']}/download").content == b'report'
    assert storage[0].get(f"{BASE}/entries/{duplicate['id']}/download").content == b'new bytes'


def test_numbering_skips_occupied_names_and_ignores_trash(storage):
    upload(storage, 'file.txt')
    first = upload(storage, 'file(1).txt')
    upload(storage, 'file(2).txt')
    assert upload(storage, 'file.txt')['name'] == 'file(3).txt'
    trash(storage, first)
    assert upload(storage, 'file.txt')['name'] == 'file(1).txt'
    other = folder(storage)
    assert upload(storage, 'file.txt', other['id'])['name'] == 'file.txt'


def test_move_rename_and_folder_copy_auto_number(storage):
    client, _, _, _, _, headers = storage
    source = folder(storage, 'source')
    target = folder(storage, 'target')
    file = upload(storage, parent=source['id'])
    upload(storage, parent=target['id'])
    moved = action(storage, file, 'move', {'parent_id': target['id']}).json()
    assert moved['name'] == 'report(1).txt'
    renamed = client.patch(f"{BASE}/entries/{file['id']}", headers=headers, json={'name':'report.txt'}).json()
    assert renamed['name'] == 'report(1).txt'
    # A no-op never adds another suffix; folders keep dots as part of the name.
    assert action(storage, renamed, 'move', {'parent_id':target['id']}).json()['name'] == renamed['name']
    dotted = folder(storage, 'project.v1')
    upload(storage, parent=dotted['id'])
    copied = action(storage, dotted, 'copy').json()
    assert copied['name'] == 'project.v1(1)'
    assert client.get(BASE + '/entries', params={'parent_id':copied['id']}).json()['items'][0]['name'] == 'report.txt'


def test_upload_names_resolved_after_overlapping_reservations(storage):
    _, store, _, users, _, _ = storage
    owner = users[0]['id']
    files = [{'name':'same.txt','size':1,'content_type':'text/plain'}] * 2
    first = store.reserve(owner, None, files)
    second = store.reserve(owner, None, files)
    # Another operation may occupy the requested name while both uploads are in flight.
    store.folder(owner, 'same.txt')
    assert [item['name'] for item in store.finish(owner, None, files, second)] == ['same(1).txt','same(2).txt']
    assert [item['name'] for item in store.finish(owner, None, files, first)] == ['same(3).txt','same(4).txt']
    assert files[0]['name'] == 'same.txt'


def test_normalized_batch_duplicates_get_distinct_names(storage):
    response = storage[0].post(BASE + '/files', headers=storage[5], files=[
        ('files', ('é.txt', b'one')), ('files', ('e\u0301.txt', b'two')),
    ])
    assert response.status_code == 201
    assert [item['name'] for item in response.json()['items']] == ['é.txt', 'é(1).txt']
    assert storage[0].get(BASE + '/capabilities').json()['name_conflict_policy'] == 'auto_rename'


def tree_upload(storage, paths, directories=(), contents=None, parent=None):
    import json
    data = {'tree': json.dumps({'paths':paths, 'directories':list(directories)})}
    if parent:
        data['parent_id'] = parent
    return storage[0].post(BASE + '/files', headers=storage[5], data=data,
                          files=[('files', (path.split('/')[-1], content, 'text/plain'))
                                 for path, content in zip(paths, contents or [b'content'] * len(paths))])


def test_folder_upload_preserves_nested_tree_empty_folders_and_duplicate_roots(storage):
    client = storage[0]
    destination = folder(storage, 'Destination')
    original = folder(storage, 'Project', destination['id'])
    paths = ['Project/notes.md', 'Project/자료/report.txt', 'Project/자료/report.txt']
    response = tree_upload(storage, paths, ['Project/empty'], [b'# Notes', b'one', b'two'], destination['id'])
    assert response.status_code == 201, response.text
    items = response.json()['items']
    by_name = {item['name']:item for item in items}
    root = by_name['Project(1)']
    assert root['parent_id'] == destination['id']
    assert by_name['자료']['parent_id'] == root['id']
    assert by_name['empty']['parent_id'] == root['id']
    assert by_name['report.txt']['parent_id'] == by_name['자료']['id']
    assert by_name['report(1).txt']['parent_id'] == by_name['자료']['id']
    assert client.get(BASE + '/entries', params={'parent_id':original['id']}).json()['items'] == []
    assert client.get(f"{BASE}/entries/{by_name['report(1).txt']['id']}/download").content == b'two'
    assert client.get(f"{BASE}/entries/{by_name['notes.md']['id']}/preview").content == b'# Notes'


def test_empty_folder_upload_needs_no_nextcloud_content(storage):
    response = tree_upload(storage, [], ['Empty/Child'])
    assert response.status_code == 201, response.text
    assert [item['name'] for item in response.json()['items']] == ['Empty', 'Child']
    assert storage[2].calls == []


@pytest.mark.parametrize('path', ['../escape.txt', '/absolute.txt', 'A//file.txt', 'A/../file.txt',
                                    'A/./file.txt', 'A\\file.txt', 'A/\x00file', '/'.join(['a'] * 33)])
def test_folder_upload_rejects_invalid_paths_before_remote_io(storage, path):
    response = tree_upload(storage, [path])
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_upload_tree'
    assert storage[2].calls == []
    assert storage[0].get(BASE + '/entries').json()['total'] == 0


@pytest.mark.parametrize('tree', ['null', '[]', '{', '{"paths":[],"directories":[]}',
    '{"paths":["one"],"directories":"bad"}', '{"paths":[1],"directories":[]}',
    '{"paths":["one"],"directories":["one"]}'])
def test_folder_upload_manifest_validation(storage, tree):
    response = storage[0].post(BASE + '/files', headers=storage[5], data={'tree':tree}, files={'files':('one', b'1')})
    assert response.status_code == 422
    assert storage[2].calls == []


def test_folder_upload_bounds_and_upstream_failure_leave_no_partial_tree(storage, monkeypatch):
    assert tree_upload(storage, [], [f'folder{i}' for i in range(1001)]).status_code == 422
    monkeypatch.setenv('FILE_STORAGE_MAX_FILES', '1')
    assert tree_upload(storage, ['Root/a', 'Root/b']).status_code == 413
    monkeypatch.setenv('FILE_STORAGE_MAX_FILE_BYTES', '2')
    assert tree_upload(storage, ['Root/a'], contents=[b'large']).status_code == 413
    assert storage[2].calls == []
    storage[2].fail_upload = True
    assert tree_upload(storage, ['Root/a'], contents=[b'1']).status_code == 502
    assert storage[0].get(BASE + '/entries').json()['total'] == 0
    assert asyncio.run(cleanup(storage[1], storage[2]))['removed'] == 1


def test_folder_upload_commit_failure_rolls_back_all_folders(storage):
    _, store, _, users, _, _ = storage
    owner = users[0]['id']
    files = [{'name':'a','size':1,'content_type':'text/plain'}]
    blobs = store.reserve(owner, None, files)
    store.abort(owner, blobs)
    with pytest.raises(AccessError):
        store.finish(owner, None, files, blobs, ['Root/Sub/a'], ['Root', 'Root/Sub'])
    assert store.list(owner)['total'] == 0


def test_folder_upload_owner_scope_and_normalized_parent_mapping(storage):
    response = tree_upload(storage, ['Cafe\u0301/notes.txt'], ['Café/Empty'])
    assert response.status_code == 201
    items = response.json()['items']
    root = next(item for item in items if item['name'] == 'Café')
    assert all(item['parent_id'] == root['id'] for item in items if item['id'] != root['id'])
    bob = (*storage[:5], storage[4]('bob'))
    assert tree_upload(bob, ['Private/a'], parent=root['id']).status_code == 404
