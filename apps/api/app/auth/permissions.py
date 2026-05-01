"""Static RBAC permission matrix.

Maps (auth_role, module) -> allowed actions. The matrix is the single source of
truth for what each role can do per IA module; it is consulted by the
`require_permission` FastAPI dependency in `app.auth.rbac`.
"""
from typing import Literal

Role = Literal["admin", "manager", "editor", "drafter", "purchase_officer", "viewer"]
Module = Literal[
    "dashboard",
    "tracking",
    "list",
    "shop_dwgs",
    "isample",
    "orderbook",
    "it_management",
]
Action = Literal["read", "write", "approve", "comment"]

_ALL_MODULES: tuple[str, ...] = (
    "dashboard",
    "tracking",
    "list",
    "shop_dwgs",
    "isample",
    "orderbook",
    "it_management",
)

MATRIX: dict[str, dict[str, set[str]]] = {
    "admin": {m: {"read", "write", "approve", "comment"} for m in _ALL_MODULES},
    "manager": {
        m: {"read", "write", "approve", "comment"}
        for m in _ALL_MODULES
        if m != "it_management"
    }
    | {"it_management": {"read"}},
    "editor": {
        m: {"read", "write", "comment"}
        for m in ("dashboard", "tracking", "list", "shop_dwgs", "isample")
    }
    | {"orderbook": {"read", "comment"}, "it_management": set()},
    "drafter": {
        "dashboard":     {"read"},
        "tracking":      {"read", "write", "approve", "comment"},
        "list":          {"read", "write", "approve", "comment"},
        "shop_dwgs":     {"read", "write", "approve", "comment"},
        "isample":       {"read"},
        "orderbook":     {"read", "write", "approve", "comment"},
        "it_management": set(),
    },
    "purchase_officer": {
        "dashboard": {"read"},
        "tracking": {"read", "comment"},
        "list": {"read"},
        "shop_dwgs": {"read"},
        "isample": {"read"},
        "orderbook": {"read", "write", "approve", "comment"},
        "it_management": set(),
    },
    "viewer": {m: {"read"} for m in _ALL_MODULES if m != "it_management"}
    | {"it_management": set()},
}


def has_permission(role: str, module: str, action: str) -> bool:
    """Return True iff `role` is allowed to perform `action` on `module`."""
    return action in MATRIX.get(role, {}).get(module, set())
