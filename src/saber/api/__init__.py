"""Read-mostly FastAPI surface. The only event path is the bounded gateway; no truth is served."""

from saber.api.app import create_app

__all__ = ["create_app"]
