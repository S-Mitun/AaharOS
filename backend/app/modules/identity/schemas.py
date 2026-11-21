"""Request bodies for the identity API."""

from pydantic import BaseModel, Field

_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=_EMAIL)
    password: str = Field(min_length=1, max_length=256)
    organization_code: str | None = Field(default=None, max_length=64)


class CreateMemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=_EMAIL)
    display_name: str = Field(min_length=1, max_length=120)
    role: str
    password: str = Field(min_length=1, max_length=256)


class CreatedResponse(BaseModel):
    id: str
