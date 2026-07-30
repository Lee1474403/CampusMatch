from datetime import date

from backend.app.models.entities import User
from backend.app.schemas.user import InterestOut, OwnProfile, PrivateProfile, UserProfile


PROFILE_FIELD_LABELS = {
    "nickname": "昵称",
    "avatar_url": "头像",
    "grade": "年级",
    "school": "学校",
    "gender": "性别",
    "location_province": "所在省份",
    "location_city": "所在城市",
    "hometown_province": "家乡省份",
    "hometown_city": "家乡城市",
    "interests": "兴趣爱好",
}


def calculate_age(birth_date: date, today: date | None = None) -> int:
    current = today or date.today()
    return current.year - birth_date.year - ((current.month, current.day) < (birth_date.month, birth_date.day))


def missing_profile_fields(user: User) -> list[str]:
    missing: list[str] = []
    for field in (
        "nickname",
        "avatar_url",
        "grade",
        "school",
        "gender",
        "location_province",
        "location_city",
        "hometown_province",
        "hometown_city",
    ):
        value = getattr(user, field, None)
        if not value or (isinstance(value, str) and not value.strip()):
            missing.append(PROFILE_FIELD_LABELS[field])
    if not user.interests:
        missing.append(PROFILE_FIELD_LABELS["interests"])
    return missing


def is_profile_complete(user: User) -> bool:
    return not missing_profile_fields(user)


def profile_from_user(user: User, *, full: bool = True) -> UserProfile:
    base = {
        "id": user.id,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
    }
    if not full:
        return UserProfile(**base)
    return UserProfile(
        **base,
        gender=user.gender,
        age=calculate_age(user.birth_date),
        school=user.school,
        department=user.department,
        grade=user.grade,
        location_province=user.location_province,
        location_city=user.location_city,
        hometown_province=user.hometown_province,
        hometown_city=user.hometown_city,
        bio=user.bio,
        interests=[InterestOut.model_validate(interest) for interest in user.interests],
    )


def own_profile_from_user(user: User) -> OwnProfile:
    public = profile_from_user(user)
    return OwnProfile(
        **public.model_dump(),
        account=user.account,
        phone=user.phone,
        email=user.email,
        real_name=user.real_name,
        wechat=user.wechat,
        real_photos=user.real_photos or [],
        birth_date=user.birth_date,
        created_at=user.created_at,
        is_superuser=user.is_superuser,
        is_matching_enabled=user.is_matching_enabled,
        profile_complete=is_profile_complete(user),
        missing_profile_fields=missing_profile_fields(user),
    )


def private_profile_from_user(user: User) -> PrivateProfile:
    return PrivateProfile(
        phone=user.phone,
        email=user.email,
        wechat=user.wechat,
        real_photos=user.real_photos or [],
    )
