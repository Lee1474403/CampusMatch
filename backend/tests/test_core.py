from datetime import UTC, date, datetime, timedelta

from pydantic import ValidationError

from backend.app.core.security import create_token, decode_token, hash_password, verify_password
from backend.app.models.entities import Interest, User
from backend.app.schemas.auth import RegisterRequest
from backend.app.schemas.user import ProfileUpdate
from backend.app.services.matching import hometown_similarity, jaccard_similarity, location_similarity, score_pair
from backend.app.services.pairing import ensure_utc, repeat_match_penalty
from backend.app.services.users import (
    is_profile_complete,
    missing_profile_fields,
    own_profile_from_user,
    private_profile_from_user,
    profile_from_user,
)


def make_user(
    user_id: int,
    gender: str,
    birthday: date,
    tags: list[Interest],
    department: str,
    province: str = "陕西",
    city: str = "西安",
    hometown_province: str | None = None,
    hometown_city: str | None = None,
) -> User:
    user = User(
        id=user_id,
        account=f"S{user_id}",
        phone=f"1380000{user_id:04d}",
        email=f"user{user_id}@example.com",
        password_hash="unused",
        nickname=f"用户{user_id}",
        gender=gender,
        birth_date=birthday,
        school="测试大学",
        department=department,
        grade="2023级",
        location_province=province,
        location_city=city,
        hometown_province=hometown_province or province,
        hometown_city=hometown_city or city,
        avatar_url="/static/test.svg",
        bio="测试简介",
        is_superuser=False,
        is_matching_enabled=False,
    )
    user.interests = tags
    return user


def test_password_hash_and_jwt_round_trip() -> None:
    password_hash = hash_password("Campus123")
    assert password_hash != "Campus123"
    assert verify_password("Campus123", password_hash)
    assert not verify_password("wrong-password", password_hash)
    token = create_token(42, "access")
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == "access"


def test_jaccard_similarity() -> None:
    assert jaccard_similarity({1, 2, 3}, {2, 3, 4}) == 0.5
    assert jaccard_similarity(set(), set()) == 0.0


def test_sqlite_naive_datetime_is_marked_as_utc() -> None:
    normalized = ensure_utc(datetime(2026, 7, 30, 1, 40))
    assert normalized is not None
    assert normalized.tzinfo is UTC
    assert normalized.isoformat() == "2026-07-30T01:40:00+00:00"


def test_repeat_match_penalty_decays_over_time() -> None:
    now = datetime(2026, 7, 30, tzinfo=UTC)
    assert repeat_match_penalty(now - timedelta(days=10), now) == 30.0
    assert repeat_match_penalty(now - timedelta(days=60), now) == 15.0
    assert repeat_match_penalty(now - timedelta(days=120), now) == 5.0
    assert repeat_match_penalty(now - timedelta(days=200), now) == 0.0


def test_candidate_score_rewards_shared_interests_and_near_age() -> None:
    music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐")
    movie = Interest(id=2, name="悬疑影视", emoji="🎬", category="动漫影视")
    coding = Interest(id=3, name="编程", emoji="💻", category="科技校园")
    viewer = make_user(1, "male", date(2004, 1, 1), [music, movie], "计算机学院")
    close_match = make_user(2, "female", date(2005, 1, 1), [music, movie], "艺术学院")
    distant_match = make_user(3, "female", date(1999, 1, 1), [coding], "计算机学院")

    close_score = score_pair(viewer, close_match, date(2026, 7, 28))
    distant_score = score_pair(viewer, distant_match, date(2026, 7, 28))
    assert close_score.score > distant_score.score
    assert close_score.shared_interests == ["华语流行", "悬疑影视"]
    assert "年龄很接近" in close_score.reasons


def test_location_score_and_preliminary_weights() -> None:
    music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐")
    left = make_user(1, "male", date(2004, 1, 1), [music], "计算机学院", "陕西省", "西安市")
    same_city = make_user(2, "female", date(2004, 1, 1), [music], "外国语学院", "陕西", "西安")
    same_province = make_user(3, "female", date(2004, 1, 1), [music], "艺术学院", "陕西", "咸阳")
    different_province = make_user(4, "female", date(2004, 1, 1), [music], "新闻学院", "四川", "成都")

    assert location_similarity(left, same_city) == 1.0
    assert location_similarity(left, same_province) == 0.6
    assert location_similarity(left, different_province) == 0.0
    assert score_pair(left, same_city, date(2026, 7, 30)).score == 100.0
    assert score_pair(left, same_province, date(2026, 7, 30)).score == 88.0
    assert score_pair(left, different_province, date(2026, 7, 30)).score == 70.0


def test_location_and_hometown_split_the_geography_weight_equally() -> None:
    music = Interest(id=1, name="华语流行", emoji="🎧", category="音乐")
    left = make_user(1, "male", date(2004, 1, 1), [music], "计算机学院")
    current_location_only = make_user(
        2,
        "female",
        date(2004, 1, 1),
        [music],
        "外国语学院",
        "陕西",
        "西安",
        "四川",
        "成都",
    )

    assert location_similarity(left, current_location_only) == 1.0
    assert hometown_similarity(left, current_location_only) == 0.0
    assert score_pair(left, current_location_only, date(2026, 7, 30)).score == 85.0


def test_profile_completion_requires_avatar_and_interests() -> None:
    user = make_user(8, "male", date(2004, 1, 1), [], "计算机学院")
    user.avatar_url = None
    assert not is_profile_complete(user)
    assert missing_profile_fields(user) == ["头像", "兴趣爱好"]
    user.avatar_url = "/uploads/avatar.png"
    user.interests = [Interest(id=8, name="编程", emoji="💻")]
    assert is_profile_complete(user)


def test_profile_completion_requires_location() -> None:
    user = make_user(9, "female", date(2004, 1, 1), [Interest(id=9, name="阅读", emoji="📚")], "文学院")
    user.location_province = None
    user.location_city = None
    assert missing_profile_fields(user) == ["所在省份", "所在城市"]
    assert not is_profile_complete(user)


def test_profile_completion_requires_hometown() -> None:
    user = make_user(10, "male", date(2004, 1, 1), [Interest(id=10, name="篮球", emoji="🏀")], "体育学院")
    user.hometown_province = None
    user.hometown_city = None
    assert missing_profile_fields(user) == ["家乡省份", "家乡城市"]
    assert not is_profile_complete(user)


def test_school_is_required_but_department_is_optional() -> None:
    user = make_user(11, "female", date(2004, 1, 1), [Interest(id=11, name="摄影", emoji="📷")], "")
    user.department = None
    assert is_profile_complete(user)

    user.school = None
    assert missing_profile_fields(user) == ["学校"]
    assert not is_profile_complete(user)


def test_registration_accepts_empty_department_but_requires_school() -> None:
    payload = RegisterRequest(
        account="20269999",
        phone="13899999999",
        email="student@example.com",
        password="Campus123",
        gender="male",
        nickname="新同学",
        birth_date=date(2005, 1, 1),
        school="测试大学",
        department=None,
        grade="2024级",
    )
    assert payload.school == "测试大学"
    assert payload.department is None
    assert ProfileUpdate(school="测试大学", department="   ").department is None

    try:
        RegisterRequest(
            account="20269998",
            phone="13899999998",
            email="student2@example.com",
            password="Campus123",
            gender="female",
            nickname="另一位同学",
            birth_date=date(2005, 1, 1),
            school="   ",
            grade="2024级",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("注册时学校不能为空")


def test_account_is_only_exposed_in_own_profile() -> None:
    user = make_user(
        12,
        "male",
        date(2004, 1, 1),
        [Interest(id=12, name="编程", emoji="💻", category="科技校园", sort_order=1)],
        None,
    )
    public_profile = profile_from_user(user)
    own_profile = own_profile_from_user(user)
    private_profile = private_profile_from_user(user)

    assert "account" not in public_profile.model_dump()
    assert "real_name" not in public_profile.model_dump()
    assert "real_name" not in private_profile.model_dump()
    assert own_profile.account == user.account
    assert "real_name" in own_profile.model_dump()
