"""Schemas for tasks (migration 0080, Plan V1 §10, Q524)."""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from ..schema_guards import no_null

TaskStatus = Literal["open", "in_progress", "done", "cancelled"]
TargetType = Literal["project", "item", "cutlist"]

# Stripped *before* the length check, so a whitespace-only title is a clean 422
# here rather than a raw CHECK violation (`ck_task_title`) from the DB.
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(max_length=5000)]


class _Targets(BaseModel):
    project_id: int | None = None
    item_id: int | None = None
    cutlist_id: int | None = None

    @model_validator(mode="after")
    def _at_most_one(self):
        if sum(v is not None for v in (self.project_id, self.item_id, self.cutlist_id)) > 1:
            raise ValueError("a task has at most one target: project_id, item_id or cutlist_id")
        return self


class CreateTaskIn(_Targets):
    title: Title
    description: Description | None = None
    assignee_id: int | None = None
    due_date: date | None = None


class PatchTaskIn(_Targets):
    """Omitted keeps the value; an explicit `null` clears a nullable one. If any of the
    three target ids is sent, the task's target becomes the one that is not null (or
    none), so moving a task is one PATCH."""
    title: Title | None = None
    description: Description | None = None
    assignee_id: int | None = None
    due_date: date | None = None
    expected_versions: dict[str, int] | None = None

    reject_null = no_null("title")


class TaskStatusIn(BaseModel):
    status: TaskStatus


class TaskOut(BaseModel):
    task_id: int
    title: str
    description: str | None
    status: TaskStatus
    assignee_id: int | None
    assignee_name: str | None
    created_by: int
    created_by_name: str | None
    due_date: date | None
    source: str
    project_id: int | None
    item_id: int | None
    cutlist_id: int | None
    target_type: TargetType | None
    target_label: str | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    field_versions: dict[str, int] = Field(default_factory=dict)
    comment_count: int = 0
    can_comment: bool = False
    created_at: datetime
    updated_at: datetime


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
