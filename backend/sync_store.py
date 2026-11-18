"""Backward-compatible re-export of SyncEventStore from store.py."""

try:
    from .store import SyncEventStore
except ImportError:
    from store import SyncEventStore

__all__ = ["SyncEventStore"]
