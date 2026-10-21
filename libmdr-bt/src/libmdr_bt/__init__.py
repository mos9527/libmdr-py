"""Python bindings for mdr-bt-shared (libmdr-bt)."""

from .connection import PlatformConnection, create_connection

__all__ = [
    "PlatformConnection",
    "create_connection",
]
