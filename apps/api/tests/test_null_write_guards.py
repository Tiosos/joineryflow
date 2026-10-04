"""An explicit `null` for a field whose column can never be NULL is a clean 422 (`schema_guards.no_null`).

Found by an audit that sent `{field: null}` to every null-accepting PATCH / PUT field on a copy of the seeded
database: 32 fields answered a raw 500 (the NOT NULL column refused the UPDATE) and one — `PATCH /suppliers`
`status` — was written, because the column is nullable and the response model types it non-null, so the
route's commit landed before the response failed validation and every later read of the row 500'd.
That one has its own HTTP test in `test_supplier_routes.py`; this file pins the whole list at the schema.

Omitting a field must still work (that is what `X | None = None` is for), so each case also checks that.
"""
import pytest
from pydantic import ValidationError

from app.cut_floor.schemas import BoardInventoryPatchIn, CutSchedulePatchIn
from app.estimating import schemas as est
from app.material_takes.schemas import PatchLineIn as TakeLineIn
from app.procurement_v1.batches.schemas import PatchBatchIn
from app.project_contacts.schemas import PatchContactIn
from app.projects.schemas import PatchProjectIn
from app.qc.schemas import PatchChecklistItemIn, PatchDefectIn, PatchReworkIn
from app.related_parts.schemas import PatchRelatedPartIn
from app.samples.schemas import PatchSampleIn
from app.suppliers.schemas import PatchSupplierIn
from app.users.schemas import UserPatch

GUARDED = {
    BoardInventoryPatchIn: ["qty_on_hand"],
    CutSchedulePatchIn: ["priority"],
    PatchRelatedPartIn: ["related_part_type_key"],
    PatchSupplierIn: ["name", "category", "status"],
    PatchSampleIn: ["title", "hex_swatch"],
    UserPatch: ["full_name", "is_active"],
    PatchBatchIn: ["qty_ordered", "qty_received"],
    PatchProjectIn: ["name"],
    PatchContactIn: ["kind", "name", "sort_order"],
    TakeLineIn: ["qty", "wastage_pct"],
    est.PatchEstimateIn: ["title"],
    est.PatchRevisionIn: ["markup_pct", "gst_pct"],
    est.PatchLineIn: ["description", "qty", "unit"],
    est.PatchPartIn: ["qty", "paint_instruction"],
    est.PatchHardwareIn: ["qty"],
    PatchDefectIn: ["description"],
    PatchChecklistItemIn: ["label", "is_checked", "sort_order"],
    PatchReworkIn: ["cause", "scope"],
}
CASES = [(model, field) for model, fields in GUARDED.items() for field in fields]


@pytest.mark.parametrize("model,field", CASES, ids=[f"{m.__module__.split('.')[-2]}.{m.__name__}.{f}" for m, f in CASES])
def test_an_explicit_null_is_refused_naming_the_field(model, field):
    with pytest.raises(ValidationError) as exc:
        model.model_validate({field: None})
    errors = exc.value.errors()
    assert [e["loc"] for e in errors if e["loc"] == (field,)], errors
    assert any("cannot be null" in e["msg"] for e in errors)


@pytest.mark.parametrize("model", list(GUARDED), ids=[m.__module__.split(".")[-2] + "." + m.__name__ for m in GUARDED])
def test_omitting_the_fields_is_still_fine(model):
    """The guard runs only for a field the caller supplied."""
    model.model_validate({})

