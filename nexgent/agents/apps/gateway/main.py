"""Gateway service entrypoint for Uvicorn and container deployments."""

from .app import app

__all__ = ["app"]
