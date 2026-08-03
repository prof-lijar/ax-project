from app.core.settings import get_settings
from app.nextcloud.client import NextcloudClient


def get_nextcloud_client() -> NextcloudClient:
    return NextcloudClient(get_settings())

