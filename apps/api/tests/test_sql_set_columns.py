"""A dynamic `UPDATE … SET {list}` must take its column names from an allow-list.

Values are always bound parameters, but a column name cannot be, so a function that
builds a `SET` list (or an interpolated table / column name) from request keys has to
name the columns it may write first: `sql_columns.require_columns(keys, ALLOWED)`, a
filter `if k in <ALLOWED_COLUMNS>` or a lookup through a column map (`columns[k]`).
This test finds the f-string statements that have none of these. A site that is safe for
another reason goes in `ALLOWED` with that reason (CLAUDE.md §8).
"""
import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
# `SET {…}`, `UPDATE {table}`, or a concatenated `"UPDATE t SET " + …`
DYNAMIC = re.compile(r"\bSET\s*\{|\bUPDATE\s+\{|\bSET\s*[\"']\s*\+", re.I)
# Evidence, in the enclosing function, that the names were checked first.
GUARDED = re.compile(
    r"require_columns\(|"
    # `if k in _PATCHABLE`, `if k in ("a", "b")`, `set(fields) - _PATCHABLE_COLUMNS`
    r"\bif\s+\w+\s+(?:not\s+)?in\s+(?:_?[A-Z][A-Z_]+\b|\()|"
    r"\bif\s+\w+\s+in\s+\w*(?:columns|allowed|insert_cols)\w*|"
    r"\)\s*-\s*_?[A-Z][A-Z_]+\b|"
    # the keys are the declared fields of a request model (`extra` is never "allow" there)
    r"\.model_dump\(|"
    # a lookup through a column map: `columns[k]`, `_PATCH_COL_MAP[k]`, `REGISTRY[type_]`
    r"\b\w*(?:COLUMN|COLS|MAP|columns|REGISTRY)\w*\[\w+\]"
)

# (file, first words of the statement): reason
ALLOWED: dict[tuple[str, str], str] = {
    ("estimating/_q_core.py", 'f""" UPDATE estimate_revision'):
        "the SET list is assembled from string literals chosen by the stage being entered",
    ("hardware_lines/queries.py", "UPDATE item_hardware_lines"):
        "`updates` keys are the literals `qty` / `note`, set one by one from the payload",
    ("parts/queries.py", "UPDATE modules"):
        "`updates` keys are the literals `name` / `notes`, set one by one from the payload",
    ("parts/queries.py", "UPDATE parts"):
        "`updates` keys are the columns of `_PART_FIELD_MAP`, a module constant",
    ("items/_q_base.py", "UPDATE items"):
        "`updates` keys are columns of `_PATCH_FIELD_MAP` plus the literal `field_versions`",
    ("related_parts/queries.py", "UPDATE items"):
        "keys come from `PatchRelatedPartIn.model_dump`; the values are bound as `:v{n}`",
}


def _sites():
    for path in sorted(APP.rglob("*.py")):
        src = path.read_text()
        tree = ast.parse(src)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.get_source_segment(src, fn) or ""
            for node in ast.walk(fn):
                if isinstance(node, (ast.Constant, ast.JoinedStr)):
                    seg = ast.get_source_segment(src, node) or ""
                    if isinstance(node, ast.JoinedStr) and DYNAMIC.search(seg):
                        yield path.relative_to(APP).as_posix(), node.lineno, seg, body
                elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                    seg = ast.get_source_segment(src, node) or ""
                    if DYNAMIC.search(seg):
                        yield path.relative_to(APP).as_posix(), node.lineno, seg, body


def test_dynamic_set_lists_use_a_column_allowlist():
    seen, bad = set(), []
    for rel, line, seg, body in _sites():
        if (rel, line) in seen:
            continue
        seen.add((rel, line))
        if GUARDED.search(body):
            continue
        if any(rel == f and key in seg for (f, key) in ALLOWED):
            continue
        bad.append(f"{rel}:{line}: {' '.join(seg.split())[:90]}")
    assert not bad, (
        "dynamic SET / identifier in SQL with no column allow-list (use "
        "sql_columns.require_columns, filter by a column map, or list it in ALLOWED with a reason):\n"
        + "\n".join(bad)
    )


def test_the_guard_catches_an_unchecked_set_list():
    unsafe = 'def f(db, fields):\n    sets = ", ".join(f"{k} = :{k}" for k in fields)\n    db.execute(text(f"UPDATE t SET {sets}"))\n'
    safe = unsafe.replace("def f(db, fields):\n", "def f(db, fields):\n    require_columns(fields, _T_COLUMNS)\n")
    assert DYNAMIC.search(unsafe) and not GUARDED.search(unsafe)
    assert GUARDED.search(safe)
