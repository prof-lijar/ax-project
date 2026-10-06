"""Retry queued blob deletions and remove abandoned uploads. Schedule periodically."""
import argparse
import asyncio
import json

from sqlalchemy import create_engine

from app.file_storage.config import load_storage_settings
from app.file_storage.service import cleanup, get_storage_client
from app.file_storage.store import StorageStore
from app.identity.config import load_identity_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    engine = create_engine(load_identity_settings().database_url, pool_pre_ping=True, hide_parameters=True)
    try:
        store = StorageStore(engine, load_storage_settings().deployment)
        store.ready()
        result = asyncio.run(cleanup(store, get_storage_client(), args.limit))
        print(json.dumps(result))
        if result["failed"]:
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
