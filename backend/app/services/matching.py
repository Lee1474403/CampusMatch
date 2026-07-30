from dataclasses import dataclass
from datetime import date

from backend.app.core.regions import normalize_city, normalize_province
from backend.app.models.entities import User
from backend.app.services.users import calculate_age


@dataclass(frozen=True)
class PairScore:
    score: float
    shared_interests: list[str]
    reasons: list[str]


def jaccard_similarity(left: set[object], right: set[object]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def location_similarity(left: User, right: User) -> float:
    return region_similarity(
        left.location_province,
        left.location_city,
        right.location_province,
        right.location_city,
    )


def hometown_similarity(left: User, right: User) -> float:
    return region_similarity(
        left.hometown_province,
        left.hometown_city,
        right.hometown_province,
        right.hometown_city,
    )


def region_similarity(
    left_province_value: str | None,
    left_city_value: str | None,
    right_province_value: str | None,
    right_city_value: str | None,
) -> float:
    left_province = normalize_province(left_province_value)
    right_province = normalize_province(right_province_value)
    left_city = normalize_city(left_city_value)
    right_city = normalize_city(right_city_value)
    if not left_province or not right_province or left_province != right_province:
        return 0.0
    if left_city and right_city and left_city == right_city:
        return 1.0
    return 0.6


def score_pair(left: User, right: User, current_date: date | None = None) -> PairScore:
    today = current_date or date.today()
    left_tags = {interest.id for interest in left.interests}
    right_tags = {interest.id for interest in right.interests}
    left_categories = {interest.category for interest in left.interests if interest.category}
    right_categories = {interest.category for interest in right.interests if interest.category}
    shared_names = sorted(interest.name for interest in right.interests if interest.id in left_tags)
    shared_categories = sorted(left_categories & right_categories)
    exact_interest_score = jaccard_similarity(left_tags, right_tags)
    category_score = jaccard_similarity(left_categories, right_categories)
    interest_score = exact_interest_score * 0.85 + category_score * 0.15

    age_gap = abs(calculate_age(left.birth_date, today) - calculate_age(right.birth_date, today))
    if age_gap <= 2:
        age_score = 1 - age_gap * 0.15
    else:
        age_score = max(0.0, 0.7 - (age_gap - 2) * 0.18)

    location_score = location_similarity(left, right)
    hometown_score = hometown_similarity(left, right)
    geography_score = location_score * 0.50 + hometown_score * 0.50
    total = interest_score * 0.60 + geography_score * 0.30 + age_score * 0.10
    reasons: list[str] = []
    if shared_names:
        reasons.append(f"共同喜欢{shared_names[0]}" + (f"等 {len(shared_names)} 项" if len(shared_names) > 1 else ""))
    elif shared_categories:
        reasons.append(f"都喜欢{shared_categories[0]}类兴趣")
    if age_gap <= 2:
        reasons.append("年龄很接近")
    if location_score == 1.0:
        reasons.append("所在地同省同市")
    elif location_score == 0.6:
        reasons.append("所在地同省")
    if hometown_score == 1.0:
        reasons.append("家乡同省同市")
    elif hometown_score == 0.6:
        reasons.append("家乡同省")
    if left.department and right.department and left.department != right.department:
        reasons.append("认识不同专业的新朋友")
    return PairScore(round(total * 100, 1), shared_names, reasons or ["今天也许会有新的默契"])
