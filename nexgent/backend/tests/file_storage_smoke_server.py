"""Local browser-test backend; real APIs, isolated SQLite and fake Nextcloud.

Run from backend/: uv run uvicorn tests.file_storage_smoke_server:app
  --host 127.0.0.1 --port 8769
Test accounts: alice (admin) / bob (member), password test-pass.
Never expose this fixture on a public interface.
"""
import os
from tempfile import TemporaryDirectory

workspace = TemporaryDirectory(prefix='nexgent-storage-ui-')
os.environ['NEXGENT_DATABASE_URL'] = f'sqlite:///{workspace.name}/storage.db'
os.environ['FILE_STORAGE_DEPLOYMENT'] = 'ui-smoke'
os.environ['AX_CHAT_FILE_ROOT'] = f'{workspace.name}/chat-files'
os.environ['AX_CHAT_ARTIFACT_ROOT'] = f'{workspace.name}/chat-artifacts'
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from app.identity.config import IdentitySettings
from app.identity.store import IdentityStore
from app.file_storage.store import StorageStore
from app.file_storage.service import get_storage_client
from app.nextcloud.client import DownloadedFile, NextcloudError
from app.main import create_app
command.upgrade(Config('alembic.ini'), 'head')
engine = create_engine(os.environ['NEXGENT_DATABASE_URL']).execution_options(schema_translate_map={'auth':None,'chat':None,'file_storage':None})
@event.listens_for(engine, 'connect')
def fk(connection, _): connection.execute('PRAGMA foreign_keys=ON')
settings = IdentitySettings(os.environ['NEXGENT_DATABASE_URL'], 'http://127.0.0.1:5187', 'local-ui-test-key-' * 4, False)
identity = IdentityStore(settings, engine)
from app.identity.models import ADMIN_ROLE_ID
users = [identity.create_user(None, username=name, name=name.title(), email='', password='test-pass', role_ids=[ADMIN_ROLE_ID] if name == 'alice' else [], group_ids=[]) for name in ('alice','bob')]

store = StorageStore(engine, 'ui-smoke')
class MemoryCloud:
    def __init__(self): self.files = {}
    async def create_folder(self, path): return 201
    async def upload_file(self, path, content, content_type): self.files[path] = content; return 201
    async def download_file(self, path):
        if path not in self.files: raise NextcloudError('missing', 404)
        return DownloadedFile(path, self.files[path], 'application/octet-stream', 'blob')
    async def delete(self, path): self.files.pop(path, None); return 204
cloud = MemoryCloud()
owner = users[0]['id']
projects = store.folder(owner, 'Projects')
store.folder(owner, 'Reports')
store.folder(owner, 'Archive')
store.folder(owner, 'Q4 planning', projects['id'])
from tests.storage_preview_fixtures import preview_files
for name, content, content_type, parent in [
    ('Brand guidelines.pdf', b'%PDF-sample', 'application/pdf', None),
    ('Meeting notes.md', b'# Meeting\nProject notes', 'text/markdown', None),
    ('Budget 2026.csv', b'Team,Budget\nDesign,5000', 'text/csv', None),
    ('Product brief.txt', b'Product brief', 'text/plain', projects['id']),
    ('팀 소개.txt', b'Team', 'text/plain', None),
    *[(name, data, mime, None) for name, data, mime in preview_files()],
]:
    files = [{'name':name,'size':len(content),'content_type':content_type}]
    ids = store.reserve(owner, parent, files)
    for blob_id in ids: cloud.files[f'ui-smoke/{owner}/{blob_id}'] = content
    store.finish(owner, parent, files, ids)
app = create_app(identity_settings=settings, identity_store=identity)
app.state.file_storage_store = store
app.dependency_overrides[get_storage_client] = lambda: cloud

@app.get('/api/file-storage-test-fixture')
def fixture_marker():
    return {'fixture': 'isolated-file-storage-smoke'}
