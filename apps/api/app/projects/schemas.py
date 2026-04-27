from datetime import date, datetime

from pydantic import BaseModel


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


class ProjectListOut(BaseModel):
    projects: list[ProjectOut]
