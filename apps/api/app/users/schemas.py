from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    auth_role: str
    jtbd_role: str | None
    is_active: bool


class UserPatch(BaseModel):
    full_name: str | None = None
    auth_role: str | None = None
    jtbd_role: str | None = None
    is_active: bool | None = None
