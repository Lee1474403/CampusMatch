import logging

import aiosmtplib
from email.message import EmailMessage

from backend.app.config import settings


logger = logging.getLogger(__name__)


async def send_email(recipient: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        logger.info("SMTP 未配置，跳过发往 %s 的邮件：%s", recipient, subject)
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
            username=settings.smtp_username,
            password=settings.smtp_password,
            start_tls=settings.smtp_start_tls,
        )
    except Exception:
        logger.exception("发送邮件失败")
