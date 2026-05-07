"""CV CSV parser — header normalisation + row coercion (sub-project #7b).

Pure function. Caller is responsible for size-checking `raw_bytes`.

Returns `(parts, errors, row_count)` so the resolver can run only over rows
that parsed cleanly. Row-level errors (invalid numerics, missing required
fields) become `CvRowError` entries rather than exceptions; structural
problems (no data, missing required column header) raise `ValueError` which
the route maps to 422.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Iterable

from .schemas import CvRowError


HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "module_no":     ("MOD", "Module", "ModuleNo", "Module #", "Mod #"),
    "part_name":     ("Part Name", "PartName", "Description", "Item"),
    "qty":           ("Qty", "Quantity", "#"),
    "len_mm":        ("Length", "Len", "L", "Length (mm)"),
    "wid_mm":        ("Width", "Wid", "W", "Width (mm)"),
    "thickness_mm":  ("Thickness", "Thk", "T"),
    "material_code": ("Material", "Material Code", "MaterialCode", "Code", "Sku"),
    "edge":          ("Edge", "Edging"),
    "colour":        ("Colour", "Color", "Finish"),
    "notes":         ("Notes", "Note", "Comment"),
}

REQUIRED_COLUMNS: tuple[str, ...] = (
    "module_no",
    "part_name",
    "qty",
    "len_mm",
    "wid_mm",
    "material_code",
)


@dataclass
class ParsedPart:
    row_index: int
    module_no: int
    part_name: str
    qty: int
    len_mm: int
    wid_mm: int
    thickness_mm: int | None
    cv_code: str
    edge: str | None
    colour: str | None
    notes: str | None


def _normalise_header(s: str) -> str:
    return s.strip().lower().replace(" ", "")


def _build_alias_lookup() -> dict[str, str]:
    out: dict[str, str] = {}
    for logical, aliases in HEADER_ALIASES.items():
        for a in aliases:
            out[_normalise_header(a)] = logical
    return out


_ALIAS_LOOKUP = _build_alias_lookup()


def _resolve_headers(raw_headers: Iterable[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for h in raw_headers:
        if h is None:
            continue
        norm = _normalise_header(h)
        if norm in _ALIAS_LOOKUP:
            resolved[h] = _ALIAS_LOOKUP[norm]
    return resolved


def _coerce_int(value: str, field: str, row_index: int) -> tuple[int | None, CvRowError | None]:
    raw = (value or "").strip()
    if raw == "":
        return None, None
    try:
        return int(raw), None
    except ValueError:
        return None, CvRowError(
            row_index=row_index,
            code="INVALID_NUMERIC",
            field=field,
            value=raw[:64],
            message=f"Could not parse '{raw}' as an integer for column {field}",
        )


def parse_csv(raw_bytes: bytes) -> tuple[list[ParsedPart], list[CvRowError], int]:
    """Parse CV-style CSV bytes into typed rows.

    Raises ValueError on structural problems (empty input, missing required
    column header). Row-level errors are returned as `CvRowError` entries.
    """
    if not raw_bytes:
        raise ValueError("empty CSV")

    text = raw_bytes.decode("utf-8", errors="replace")
    if not text.strip():
        raise ValueError("empty CSV")

    reader = csv.DictReader(io.StringIO(text))
    raw_fields = reader.fieldnames or []
    if not raw_fields:
        raise ValueError("empty CSV")

    header_map = _resolve_headers(raw_fields)
    logical_to_raw: dict[str, str] = {v: k for k, v in header_map.items()}
    missing = [c for c in REQUIRED_COLUMNS if c not in logical_to_raw]
    if missing:
        raise ValueError(f"missing required column: {missing[0]}")

    parts: list[ParsedPart] = []
    errors: list[CvRowError] = []
    row_index = 0

    for row in reader:
        row_index += 1

        def _get(logical: str) -> str:
            raw_col = logical_to_raw.get(logical)
            if raw_col is None:
                return ""
            return (row.get(raw_col) or "").strip()

        part_name = _get("part_name")
        material_code = _get("material_code")

        if not part_name:
            errors.append(CvRowError(
                row_index=row_index,
                code="MISSING_REQUIRED",
                field="part_name",
                value=None,
                message="part_name is required",
            ))
            continue
        if not material_code:
            errors.append(CvRowError(
                row_index=row_index,
                code="MISSING_REQUIRED",
                field="material_code",
                value=None,
                message="material_code is required",
            ))
            continue

        module_no, e = _coerce_int(_get("module_no"), "module_no", row_index)
        if e:
            errors.append(e)
            continue
        if module_no is None:
            errors.append(CvRowError(
                row_index=row_index, code="MISSING_REQUIRED",
                field="module_no", value=None, message="module_no is required",
            ))
            continue

        qty, e = _coerce_int(_get("qty"), "qty", row_index)
        if e:
            errors.append(e)
            continue
        if qty is None:
            errors.append(CvRowError(
                row_index=row_index, code="MISSING_REQUIRED",
                field="qty", value=None, message="qty is required",
            ))
            continue

        len_mm, e = _coerce_int(_get("len_mm"), "len_mm", row_index)
        if e:
            errors.append(e)
            continue
        if len_mm is None:
            errors.append(CvRowError(
                row_index=row_index, code="MISSING_REQUIRED",
                field="len_mm", value=None, message="len_mm is required",
            ))
            continue

        wid_mm, e = _coerce_int(_get("wid_mm"), "wid_mm", row_index)
        if e:
            errors.append(e)
            continue
        if wid_mm is None:
            errors.append(CvRowError(
                row_index=row_index, code="MISSING_REQUIRED",
                field="wid_mm", value=None, message="wid_mm is required",
            ))
            continue

        if qty <= 0 or len_mm <= 0 or wid_mm <= 0:
            errors.append(CvRowError(
                row_index=row_index,
                code="INVALID_DIMENSION",
                field="qty/len_mm/wid_mm",
                value=f"{qty}/{len_mm}/{wid_mm}",
                message="qty, len_mm, wid_mm must all be > 0",
            ))
            continue

        thickness_mm, e = _coerce_int(_get("thickness_mm"), "thickness_mm", row_index)
        if e:
            errors.append(e)
            continue

        edge = _get("edge") or None
        colour = _get("colour") or None
        notes = _get("notes") or None

        parts.append(ParsedPart(
            row_index=row_index,
            module_no=module_no,
            part_name=part_name,
            qty=qty,
            len_mm=len_mm,
            wid_mm=wid_mm,
            thickness_mm=thickness_mm,
            cv_code=material_code,
            edge=edge,
            colour=colour,
            notes=notes,
        ))

    return parts, errors, row_index
