"""Atomic per-workspace counters (workspace_counter table).

Used by sub-projects #12 (PO numbers), #13 (invoice / variation numbers),
and any future feature that needs a workspace-scoped monotonic integer.

Public surface: counters.next_value(db, workspace_id=..., name=...).
"""
from .queries import next_value

__all__ = ["next_value"]
