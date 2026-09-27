"""Field-level optimistic concurrency (Plan V1 §12, Q511/Q512).

Q511 confirmed optimistic concurrency control on exactly three surfaces —
the item editor, the cutlist, and orders — because doing it everywhere would
touch all ~181 existing mutating endpoints for no benefit; everywhere else
stays last-write-wins. Q512 confirmed it must be **field-level**, with real
per-field versioning, not row-level: two people editing different fields of
the same record should never collide (Q366) — only a genuine same-field
conflict should.

Each of the three surfaces (`items`, `cutlist`, `purchase_orders`) carries a
`field_versions jsonb` column: one integer counter per field name, bumped by
`bump_field_versions` every time that field is actually written. A caller
MAY submit `expected_versions: {field: version}` on a PATCH, read from a
prior GET's own `field_versions`. `check_field_conflicts` compares each named
field's expected version against the field's current one; a mismatch is a
real conflict (someone else wrote that exact field since this caller last
read it) and the caller's whole PATCH is refused with 409 naming just the
conflicting fields, per Q366 — nothing is silently overwritten (§14).

Omitting `expected_versions` entirely, or omitting one field from it, keeps
last-write-wins for that field. This is additive: every existing caller of
these three modules that predates this migration keeps working unchanged.
"""

FieldVersions = dict[str, int]


def check_field_conflicts(
    current_versions: FieldVersions | None,
    expected_versions: FieldVersions | None,
) -> dict[str, dict]:
    """Return {field: {expected, current}} for every field whose version has
    moved on since the caller's `expected_versions` were read. Empty dict
    means no conflict (including when `expected_versions` is falsy)."""
    if not expected_versions:
        return {}
    current_versions = current_versions or {}
    conflicts: dict[str, dict] = {}
    for field, expected in expected_versions.items():
        current = current_versions.get(field, 0)
        if current != expected:
            conflicts[field] = {"expected": expected, "current": current}
    return conflicts


def bump_field_versions(
    current_versions: FieldVersions | None, changed_fields: list[str]
) -> FieldVersions:
    """The new field_versions map after writing `changed_fields`."""
    out = dict(current_versions or {})
    for f in changed_fields:
        out[f] = out.get(f, 0) + 1
    return out
