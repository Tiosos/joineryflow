"""Pydantic response schemas for the home dashboard endpoint."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class MetricCard(BaseModel):
    key: str
    label: str
    value: int | float
    href: str


class MyDayItem(BaseModel):
    item_id: int
    project_code: str
    description: str | None
    next_due_stage_key: str | None
    next_due_date: date | None


class DeliveryToday(BaseModel):
    batch_id: int
    project_code: str
    supplier: str
    eta: date


class TeamActivityRow(BaseModel):
    actor_name: str
    event: str
    target: str | None
    ts: datetime


class FavouriteProject(BaseModel):
    id: int
    project_code: str
    name: str


class HomeDashboardOut(BaseModel):
    role_view: Literal["ceo", "pm", "drafter", "purchase_officer", "viewer"]
    metrics: list[MetricCard]
    my_day: list[MyDayItem]
    deliveries_today: list[DeliveryToday]
    team_activity: list[TeamActivityRow]
    favourite_projects: list[FavouriteProject]
    all_projects_count: int
