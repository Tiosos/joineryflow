"""Shared input guards for PATCH bodies.

A PATCH schema types a field `X | None = None` so the caller can *omit* it, but
that also lets a caller send an explicit `null`. For a column that is `NOT NULL`
the null reached the UPDATE and came back as a raw 500; for a *nullable* column
that a response model types as non-null it was worse: the null was written, the
route committed before FastAPI validated the response, and every later read of
the row 500'd (`PATCH /orders` `status: null`, `PATCH /suppliers` `status: null`).

`no_null(...)` refuses an explicit null with a clean 422 that names the field.
It is a `field_validator`, so it runs only for a field the caller **supplied** —
an omitted field is untouched. Use it for the fields whose column can never
legitimately become NULL; leave it off a field that *clears* (a note, a date).

    class PatchThingIn(BaseModel):
        name: str | None = None
        reject_null = no_null("name")
"""
from pydantic import ValidationInfo, field_validator


def no_null(*fields: str):
    @field_validator(*fields)
    @classmethod
    def _no_null(cls, v, info: ValidationInfo):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v

    return _no_null
