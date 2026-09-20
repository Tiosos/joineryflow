from datetime import date, datetime

from pydantic import BaseModel, model_validator


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

    @model_validator(mode="after")
    def pm_id_not_null_if_set(self) -> "PatchProjectIn":
        if "pm_id" in self.model_fields_set and self.pm_id is None:
            raise ValueError("pm_id cannot be set to null via PATCH")
        return self


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
    # Q408's Project Details tiles (C5) — existing columns, newly served.
    created_by: str | None = None
    tg_solid: bool | None = None
    total_line_items: int | None = None


class ProjectListOut(BaseModel):
    projects: list[ProjectOut]
