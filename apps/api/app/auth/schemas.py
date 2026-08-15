from pydantic import BaseModel


class LoginIn(BaseModel):
    workspace_slug: str
    # Plain str (not EmailStr): user creation enforces format upstream; login
    # is keyed by (workspace_slug, email) and must accept seed emails like
    # `*.hartwood.test` (RFC 6761 reserved TLD that email-validator rejects).
    email: str
    password: str


class MeOut(BaseModel):
    id: int
    workspace_id: int
    email: str
    full_name: str
    auth_role: str
    jtbd_role: str | None = None
    # `{module: [actions]}` for this user's role — the RBAC matrix stays the
    # single source of truth and the web tier reads it from here.
    permissions: dict[str, list[str]] = {}
