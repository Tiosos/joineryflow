from pydantic import BaseModel, Field

from ..schema_guards import no_null


class PaymentMethodOut(BaseModel):
    payment_method_id: int
    name: str
    is_active: bool


class PaymentMethodListOut(BaseModel):
    payment_methods: list[PaymentMethodOut]


class PaymentMethodIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PatchPaymentMethodIn(BaseModel):
    reject_null = no_null("name", "is_active")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
