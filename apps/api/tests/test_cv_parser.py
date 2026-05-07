"""Tests for the CV CSV parser (sub-project #7b)."""
import pytest

from app.cv.parser import parse_csv


def test_parse_canonical_header():
    csv = (
        b"Module,Part Name,Qty,Length,Width,Material\n"
        b"1,Side Panel L,1,720,580,18-PB\n"
        b"1,Side Panel R,1,720,580,18-PB\n"
    )
    parts, errors, n = parse_csv(csv)
    assert n == 2
    assert errors == []
    assert len(parts) == 2
    assert parts[0].module_no == 1
    assert parts[0].part_name == "Side Panel L"
    assert parts[0].qty == 1
    assert parts[0].len_mm == 720
    assert parts[0].wid_mm == 580
    assert parts[0].cv_code == "18-PB"


def test_parse_alias_headers():
    csv = (
        b"MOD,Description,Qty,L,W,Code\n"
        b"2,Bottom,4,500,300,18-PB\n"
    )
    parts, errors, n = parse_csv(csv)
    assert n == 1
    assert errors == []
    assert parts[0].module_no == 2
    assert parts[0].part_name == "Bottom"
    assert parts[0].qty == 4
    assert parts[0].cv_code == "18-PB"


def test_missing_required_column_raises():
    csv = (
        b"Module,Part Name,Qty,Length,Width\n"  # no Material
        b"1,A,1,100,100\n"
    )
    with pytest.raises(ValueError, match="material_code"):
        parse_csv(csv)


def test_invalid_numeric_produces_row_error():
    csv = (
        b"Module,Part Name,Qty,Length,Width,Material\n"
        b"1,Bad,1,abc,580,18-PB\n"
        b"1,Good,1,720,580,18-PB\n"
    )
    parts, errors, n = parse_csv(csv)
    assert n == 2
    assert len(errors) == 1
    assert errors[0].code == "INVALID_NUMERIC"
    assert errors[0].field == "len_mm"
    assert len(parts) == 1
    assert parts[0].part_name == "Good"


def test_invalid_dimension_produces_row_error():
    csv = (
        b"Module,Part Name,Qty,Length,Width,Material\n"
        b"1,Zero,0,720,580,18-PB\n"
    )
    parts, errors, n = parse_csv(csv)
    assert n == 1
    assert len(errors) == 1
    assert errors[0].code == "INVALID_DIMENSION"
    assert parts == []


def test_empty_part_name_produces_row_error():
    csv = (
        b"Module,Part Name,Qty,Length,Width,Material\n"
        b"1,,1,720,580,18-PB\n"
    )
    parts, errors, n = parse_csv(csv)
    assert len(errors) == 1
    assert errors[0].code == "MISSING_REQUIRED"
    assert errors[0].field == "part_name"


def test_empty_material_code_produces_row_error():
    csv = (
        b"Module,Part Name,Qty,Length,Width,Material\n"
        b"1,A,1,720,580,\n"
    )
    parts, errors, n = parse_csv(csv)
    assert len(errors) == 1
    assert errors[0].code == "MISSING_REQUIRED"
    assert errors[0].field == "material_code"


def test_thickness_optional():
    csv = (
        b"Module,Part Name,Qty,Length,Width,Material\n"
        b"1,A,1,720,580,18-PB\n"
    )
    parts, errors, n = parse_csv(csv)
    assert parts[0].thickness_mm is None


def test_thickness_parsed_when_present():
    csv = (
        b"Module,Part Name,Qty,Length,Width,Thickness,Material\n"
        b"1,A,1,720,580,18,18-PB\n"
    )
    parts, errors, n = parse_csv(csv)
    assert parts[0].thickness_mm == 18


def test_unicode_part_name():
    csv = (
        "Module,Part Name,Qty,Length,Width,Material\n"
        "1,Côté,1,720,580,18-PB\n"
    ).encode("utf-8")
    parts, errors, n = parse_csv(csv)
    assert parts[0].part_name == "Côté"


def test_empty_csv_raises():
    with pytest.raises(ValueError, match="empty CSV"):
        parse_csv(b"")
    with pytest.raises(ValueError, match="empty CSV"):
        parse_csv(b"   \n  \n")


def test_optional_edge_colour_notes():
    csv = (
        b"Module,Part Name,Qty,Length,Width,Material,Edge,Colour,Notes\n"
        b"1,A,1,720,580,18-PB,2mmABS,Walnut,handled\n"
    )
    parts, _, _ = parse_csv(csv)
    assert parts[0].edge == "2mmABS"
    assert parts[0].colour == "Walnut"
    assert parts[0].notes == "handled"
