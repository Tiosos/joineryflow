from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ── Contacts / lift access / labour hours sub-objects ────────────────────────

ContactKind = Literal["office", "site"]


class ProjectContactOut(BaseModel):
    contact_id: int
    project_id: int
    kind: ContactKind
    position: str | None = None
    name: str
    email: str | None = None
    mobile: str | None = None
    notes: str | None = None
    sort_order: int = 0
    created_at: datetime
    created_by: int | None = None


class ProjectLiftAccessOut(BaseModel):
    project_id: int
    notes: str | None = None
    sketch_file_blob_id: int | None = None
    updated_at: datetime | None = None
    updated_by: int | None = None


class ProjectLabourHoursOut(BaseModel):
    site_install: float = 0
    assembly: float = 0
    administration: float = 0


# ── Create / patch ───────────────────────────────────────────────────────────

class CreateProjectIn(BaseModel):
    project_code: str
    name: str
    pm_id: int | None = None
    install_start: date | None = None


class PatchProjectIn(BaseModel):
    name: str | None = None
    pm_id: int | None = None
    install_start: date | None = None
    status: str | None = None
    # Project Detail 2.0 enrichment (#11) — additive
    builder: str | None = None
    classification: str | None = None
    site_street: str | None = None
    site_suburb: str | None = None
    site_postcode: str | None = None
    site_state: str | None = None
    tg_project_manager: str | None = None
    tg_coordinator: str | None = None
    tg_solid: bool | None = None
    carell_pid: str | None = None
    total_value: float | None = None
    total_line_items: int | None = None

    @model_validator(mode="after")
    def pm_id_not_null_if_set(self) -> "PatchProjectIn":
        if "pm_id" in self.model_fields_set and self.pm_id is None:
            raise ValueError("pm_id cannot be set to null via PATCH")
        return self


# ── ProjectOut ───────────────────────────────────────────────────────────────

class ProjectOut(BaseModel):
    id: int
    project_code: str
    name: str
    pm_id: int | None
    pm_name: str | None
    status: str | None
    item_count: int
    total_value: float | None
    install_start: date | None
    is_favourite: bool
    created_at: datetime
    # Project Detail 2.0 (#11) — additive
    builder: str | None = None
    classification: str | None = None
    site_street: str | None = None
    site_suburb: str | None = None
    site_postcode: str | None = None
    site_state: str | None = None
    tg_project_manager: str | None = None
    tg_coordinator: str | None = None
    tg_solid: bool | None = None
    carell_pid: str | None = None
    total_line_items: int | None = None
    closed_at: datetime | None = None
    closed_by: int | None = None
    closed_by_name: str | None = None
    contacts: list[ProjectContactOut] = Field(default_factory=list)
    lift_access: ProjectLiftAccessOut | None = None
    labour_hours: ProjectLabourHoursOut = Field(default_factory=ProjectLabourHoursOut)


class ProjectListOut(BaseModel):
    projects: list[ProjectOut]


# ── Close-out ────────────────────────────────────────────────────────────────

class CloseOutOut(BaseModel):
    project_id: int
    closed_at: datetime
    closed_by: int
    closed_by_name: str | None = None
