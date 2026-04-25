from pydantic import BaseModel, EmailStr


class LoginIn(BaseModel):
    workspace_slug: str
    email: EmailStr
    password: str


class MeOut(BaseModel):
    id: int
    workspace_id: int
    email: str
    full_name: str
    auth_role: str
