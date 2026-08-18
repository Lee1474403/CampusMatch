import logging

import aiosmtplib
from email.message import EmailMessage

from backend.app.config import settings


logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


async def send_email(recipient: str, subject: str, body: str, *, required: bool = False) -> None:
    if not settings.smtp_host:
        if required:
            raise EmailDeliveryError("SMTP 邮件服务尚未配置")
        logger.warning("SMTP 未配置，已跳过非关键邮件：%s", subject)
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_login,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls if settings.smtp_use_tls is not None else settings.smtp_port == 465,
            start_tls=False
            if (settings.smtp_use_tls if settings.smtp_use_tls is not None else settings.smtp_port == 465)
            else settings.smtp_start_tls,
        )
    except Exception as exc:
        logger.exception("发送邮件失败")
        if required:
            raise EmailDeliveryError("验证邮件发送失败") from exc


async def send_verification_email(recipient: str, token: str) -> None:
    verification_url = f"{settings.public_frontend_url}/verify-email?token={token}"
    body = (
        "欢迎加入 CampusMatch！\n\n"
        "请点击下面的链接验证邮箱，验证后才能登录：\n"
        f"{verification_url}\n\n"
        f"该链接将在 {settings.email_verification_expire_hours} 小时后失效。"
        "如果这不是你的操作，请忽略本邮件。"
    )
    await send_email(recipient, "CampusMatch 邮箱验证", body, required=True)
