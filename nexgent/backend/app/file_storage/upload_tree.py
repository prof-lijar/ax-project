"""Bounded, relative logical paths for an atomic folder upload."""
import json

from app.file_storage.schemas import validate_name
from app.identity.store import AccessError

MAX_UPLOAD_FOLDERS = 1000
MAX_UPLOAD_DEPTH = 32
MAX_MANIFEST_BYTES = 256 * 1024


def parse_tree(raw, file_count):
    if raw is None:
        return None, []
    try:
        if len(raw.encode('utf-8')) > MAX_MANIFEST_BYTES:
            raise ValueError('manifest too large')
        tree = json.loads(raw)
        if not isinstance(tree, dict) or set(tree) != {'paths', 'directories'}:
            raise ValueError('invalid manifest')
        paths, directories = tree['paths'], tree['directories']
        if (not isinstance(paths, list) or not isinstance(directories, list)
                or len(paths) != file_count or len(directories) > MAX_UPLOAD_FOLDERS):
            raise ValueError('invalid counts')

        def clean(path):
            if not isinstance(path, str):
                raise ValueError('invalid path')
            parts = path.split('/')
            if len(parts) > MAX_UPLOAD_DEPTH:
                raise ValueError('too deep')
            return '/'.join(validate_name(part) for part in parts)

        paths = [clean(path) for path in paths]
        folders = set()
        for path in [*paths, *[clean(path) + '/' for path in directories]]:
            parts = path.split('/')
            for index in range(1, len(parts)):
                folders.add('/'.join(parts[:index]))
                if len(folders) > MAX_UPLOAD_FOLDERS:
                    raise ValueError('too many folders')
        if folders.intersection(paths) or (not paths and not folders):
            raise ValueError('file/folder overlap or empty tree')
        return paths, sorted(folders, key=lambda path: (path.count('/'), path))
    except (ValueError, TypeError, RecursionError) as exc:
        raise AccessError(422, 'invalid_upload_tree') from exc
