"""Schemas for comments (migration 0042, Plan V1 §29)."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

ObjectType = Literal["project", "area", "room", "item"]

# Stripped *before* the length check, so a whitespace-only body is a clean 422
# here rather than a raw CHECK violation (`ck_comment_body_len`) from the DB.
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class CreateCommentIn(BaseModel):
    """A top-level comment names its object; a reply names only its parent —
    the reply inherits the parent's object, so it can never disagree with it."""
    object_type: ObjectType | None = None
    object_id: int | None = None
    parent_id: int | None = None
    body: Body
    mentioned_user_ids: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _one_target(self):
        has_object = self.object_type is not None or self.object_id is not None
        if self.parent_id is not None:
            if has_object:
                raise ValueError("a reply names its parent only, not an object")
        elif self.object_type is None or self.object_id is None:
            raise ValueError("object_type and object_id are required without parent_id")
        return self


class EditCommentIn(BaseModel):
    body: Body
    # None keeps the current mentions; a list (even empty) replaces them.
    mentioned_user_ids: list[int] | None = Field(default=None, max_length=20)


class MentionOut(BaseModel):
    user_id: int
    full_name: str | None = None


class CommentOut(BaseModel):
    comment_id: int
    object_type: ObjectType
    object_id: int
    parent_comment_id: int | None
    author_id: int | None
    author_name: str | None = None
    body: str
    created_at: datetime
    edited_at: datetime | None
    deleted: bool
    mentions: list[MentionOut] = Field(default_factory=list)
    replies: list["CommentOut"] = Field(default_factory=list)


class CommentThreadOut(BaseModel):
    comments: list[CommentOut]


class CommentCountsOut(BaseModel):
    """Live (non-deleted) comment counts for one project's areas and rooms,
    keyed by id. An area or room with no comments is simply absent."""
    areas: dict[int, int]
    rooms: dict[int, int]
