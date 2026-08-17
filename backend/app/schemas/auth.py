from datetime import date
import re

from pydantic import BaseModel, EmailStr, Field, field_validator


PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,72}$")
PHONE_PATTERN = re.compile(r"^\+?\d{6,20}$")


class RegisterRequest(BaseModel):
    account: str = Field(min_length=1, max_length=32)
    phone: str = Field(min_length=6, max_length=24)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    gender: str
    real_name: str | None = Field(default=None, max_length=40)
    nickname: str = Field(min_length=1, max_length=40)
    birth_date: date
    school: str = Field(min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=80)
    grade: str = Field(min_length=1, max_length=24)
    height_cm: int | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=30, le=300)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not PASSWORD_PATTERN.match(value):
            raise ValueError("密码至少 8 位，并且必须同时包含字母和数字")
        if len(value.encode("utf-8")) > 72:
            raise ValueError("密码的 UTF-8 编码不能超过 72 字节")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not PHONE_PATTERN.match(value.strip()):
            raise ValueError("手机号只能包含数字，并可使用一个开头的 + 号")
        return value.strip()

    @field_validator("account")
    @classmethod
    def validate_account(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("账号不能为空")
        if any(character.isspace() for character in normalized):
            raise ValueError("账号不能包含空格")
        return normalized

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"male", "female"}:
            raise ValueError("性别必须为 male 或 female")
        return normalized

    @field_validator("phone", "nickname", "department", "grade", "real_name")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("school")
    @classmethod
    def validate_school(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("学校不能为空")
        return value.strip()


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not PASSWORD_PATTERN.match(value):
            raise ValueError("新密码至少 8 位，并且必须同时包含字母和数字")
        if len(value.encode("utf-8")) > 72:
            raise ValueError("新密码的 UTF-8 编码不能超过 72 字节")
        return value


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
