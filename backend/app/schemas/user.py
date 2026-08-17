from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from backend.app.core.regions import normalize_city, normalize_province
from backend.app.schemas.auth import PHONE_PATTERN


class InterestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    emoji: str
    category: str = "其他"
    sort_order: int = 0


class UserSummary(BaseModel):
    id: int
    nickname: str
    avatar_url: str | None = None


class UserProfile(UserSummary):
    gender: str | None = None
    age: int | None = None
    school: str | None = None
    department: str | None = None
    grade: str | None = None
    location_province: str | None = None
    location_city: str | None = None
    hometown_province: str | None = None
    hometown_city: str | None = None
    height_cm: int | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=30, le=300)
    bio: str | None = None
    interests: list[InterestOut] = Field(default_factory=list)


class OwnProfile(UserProfile):
    account: str
    phone: str
    email: EmailStr
    real_name: str | None = None
    wechat: str | None = None
    real_photos: list[str] = Field(default_factory=list)
    birth_date: date
    created_at: datetime | None = None
    is_superuser: bool = False
    is_matching_enabled: bool = False
    profile_complete: bool = False
    missing_profile_fields: list[str] = Field(default_factory=list)


class PrivateProfile(BaseModel):
    phone: str
    email: EmailStr
    wechat: str | None = None
    real_photos: list[str] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    phone: str | None = Field(default=None, min_length=6, max_length=24)
    email: EmailStr | None = None
    nickname: str | None = Field(default=None, min_length=1, max_length=40)
    real_name: str | None = Field(default=None, max_length=40)
    wechat: str | None = Field(default=None, max_length=80)
    birth_date: date | None = None
    school: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=80)
    grade: str | None = Field(default=None, min_length=1, max_length=24)
    location_province: str | None = Field(default=None, min_length=1, max_length=40)
    location_city: str | None = Field(default=None, min_length=1, max_length=40)
    hometown_province: str | None = Field(default=None, min_length=1, max_length=40)
    hometown_city: str | None = Field(default=None, min_length=1, max_length=40)
    height_cm: int | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=30, le=300)
    bio: str | None = Field(default=None, max_length=200)
    interest_ids: list[int] | None = None

    @field_validator("phone", "nickname", "real_name", "wechat", "grade", "bio")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("department")
    @classmethod
    def normalize_optional_department(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("school")
    @classmethod
    def validate_school(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("学校不能为空")
        return value.strip()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is not None and not PHONE_PATTERN.match(value.strip()):
            raise ValueError("手机号只能包含数字，并可使用一个开头的 + 号")
        return value.strip() if value is not None else None

    @field_validator("location_province", "hometown_province")
    @classmethod
    def validate_location_province(cls, value: str | None) -> str | None:
        return normalize_province(value)

    @field_validator("location_city", "hometown_city")
    @classmethod
    def validate_location_city(cls, value: str | None) -> str | None:
        return normalize_city(value)
