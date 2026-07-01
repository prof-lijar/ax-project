from functools import lru_cache
import os


class SettingsError(RuntimeError):
    pass


class Settings:
    def __init__(self) -> None:
        self.nextcloud_url = self._required("NC_URL").rstrip("/")
        self.nextcloud_user = self._required("NC_USER")
        self.nextcloud_password = self._required("NC_PASS")
        self.nextcloud_verify_ssl = self._bool("NC_VERIFY_SSL", default=True)
        self.nextcloud_timeout_seconds = float(os.getenv("NC_TIMEOUT_SECONDS", "30"))

    @staticmethod
    def _required(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise SettingsError(f"Missing required environment variable: {name}")
        return value

    @staticmethod
    def _bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

