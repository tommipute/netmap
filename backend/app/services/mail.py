"""Server di posta (Amministrazione → Email) e invio delle email: lo usano i canali di avviso email, salvo quelli
con un server loro (`AlertChannel.smtp_custom`). Solo libreria standard (smtplib)."""
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secrets import SecretError, decrypt
from app.models import MailSettings

TIMEOUT = 10


class MailError(Exception):
    pass


@dataclass
class SmtpConfig:
    host: str | None
    port: int | None = None
    security: str | None = "starttls"
    username: str | None = None
    password_enc: str | None = None
    sender: str | None = None


def settings_row(db: Session) -> MailSettings:
    row = db.scalar(select(MailSettings).order_by(MailSettings.id).limit(1))
    if row is None:
        row = MailSettings()
        db.add(row)
        db.flush()
    return row


def configured(db: Session) -> bool:
    return bool(db.scalar(select(MailSettings.host).order_by(MailSettings.id).limit(1)))


def config_of(row: MailSettings) -> SmtpConfig:
    return SmtpConfig(row.host, row.port, row.security, row.username, row.password_enc, row.sender)


def default_port(security: str | None) -> int:
    return 465 if security == "ssl" else 25 if security == "none" else 587


def send_mail(cfg: SmtpConfig, to: list[str], subject: str, text: str) -> None:
    if not cfg.host:
        raise MailError("Manca il server di posta: impostalo in Amministrazione → Email")
    if not to:
        raise MailError("Mancano i destinatari")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = cfg.sender or cfg.username or "netmap@localhost"
    message["To"] = ", ".join(to)
    message.set_content(text)
    security = cfg.security or "starttls"
    try:
        password = decrypt(cfg.password_enc) if cfg.password_enc else ""
    except SecretError as exc:
        raise MailError(str(exc)) from exc
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(cfg.host, cfg.port or default_port(security), timeout=TIMEOUT,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(cfg.host, cfg.port or default_port(security), timeout=TIMEOUT)
        with server:
            if security == "starttls":
                server.starttls(context=ssl.create_default_context())
            if cfg.username:
                server.login(cfg.username, password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"Invio email non riuscito: {exc}") from exc
