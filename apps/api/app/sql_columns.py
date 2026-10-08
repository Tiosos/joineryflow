"""Allow-list for column names that a query builds into a dynamic `SET` list.

Values are always bound parameters; column names cannot be, so a patch function names
the columns it may write and refuses anything else before any SQL is built.
"""
from __future__ import annotations

from collections.abc import Iterable


def require_columns(keys: Iterable[str], allowed: frozenset[str]) -> None:
    """Raise ValueError if `keys` names a column outside `allowed` (a programming error,
    not bad input: request schemas already limit what a client can send)."""
    unknown = sorted(set(keys) - allowed)
    if unknown:
        raise ValueError(f"not a patchable column: {', '.join(unknown)}")
