def normalize_province(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = "".join(value.strip().split())
    for suffix in ("特别行政区", "维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "省", "市"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized or None


def normalize_city(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = "".join(value.strip().split())
    if normalized.endswith("市"):
        normalized = normalized[:-1]
    return normalized or None
