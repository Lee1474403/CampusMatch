import logging
from datetime import UTC, datetime

from fastapi import Request

from backend.app.core.rate_limit import client_ip


logger = logging.getLogger("campusmatch.audit")


def mask_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    if not separator:
        return "***"
    visible = local[:1] if local else ""
    return f"{visible}***@{domain}"


def mask_phone(value: str) -> str:
    if len(value) < 7:
        return "***"
    return f"{value[:3]}****{value[-4:]}"


def mask_identifier(value: str) -> str:
    normalized = value.strip()
    if "@" in normalized:
        return mask_email(normalized)
    if normalized.replace("+", "", 1).isdigit():
        return mask_phone(normalized)
    if len(normalized) <= 4:
        return "***"
    return f"{normalized[:2]}***{normalized[-2:]}"


def audit_event(
    request: Request,
    action: str,
    *,
    user_id: int | None = None,
    identifier: str | None = None,
    outcome: str = "success",
    detail: str | None = None,
) -> None:
    logger.info(
        "time=%s action=%s outcome=%s user_id=%s identifier=%s ip=%s user_agent=%s detail=%s",
        datetime.now(UTC).isoformat(),
        action,
        outcome,
        user_id if user_id is not None else "-",
        mask_identifier(identifier) if identifier else "-",
        client_ip(request),
        request.headers.get("user-agent", "-")[:255],
        detail or "-",
    )
