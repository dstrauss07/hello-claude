"""Send mail through Gmail (or any SMTP server) using an app password."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def recipients() -> list[str]:
    return [a.strip() for a in os.getenv("EMAIL_TO", "").split(",") if a.strip()]


def send(subject: str, html: str, text: str, attachments: dict[str, str] | None = None) -> bool:
    """Returns False (and sends nothing) when SMTP isn't configured."""
    user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    to = recipients()
    if not (user and password and to):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("EMAIL_FROM", user)
    msg["To"] = ", ".join(to)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    for name, body in (attachments or {}).items():
        msg.add_attachment(body.encode(), maintype="text", subtype="markdown", filename=name)
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=60) as s:
        s.login(user, password)
        s.send_message(msg)
    return True
