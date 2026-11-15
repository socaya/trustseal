"""Transactional email transport.

Two transports:

* ``smtp`` — production path. Uses the stdlib ``smtplib`` with the
  ``MAIL_*`` config values already present in :mod:`config`. No
  Flask-Mail dependency so the build stays self-contained.
* ``memory`` — test path. Appends each message to
  ``app.extensions['_outbox']``. Tests inspect that list to assert
  on the subject/body/recipient rather than running a real SMTP
  server. The transport is selected by ``MAIL_TRANSPORT`` so test
  code never accidentally writes to the SMTP backend.

The service always rendered the message body upstream — this module
only handles delivery and framing.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Iterable, Optional

from flask import current_app

log = logging.getLogger(__name__)


class EmailError(RuntimeError):
    """Raised for configuration failures that must not be silently swallowed."""


@dataclass(frozen=True)
class EmailMessage:
    """One rendered outbound email.

    ``body_html`` is optional. When supplied, the outbound message is
    ``multipart/alternative`` with both text and HTML parts; the HTML
    part is the richer alternative.
    """

    to: str
    subject: str
    body_text: str
    body_html: Optional[str] = None
    sender: Optional[str] = None
    reply_to: Optional[str] = None
    headers: dict = field(default_factory=dict)


def send(message: EmailMessage) -> None:
    """Deliver ``message`` using the configured transport."""
    if not message.to or "@" not in message.to:
        raise EmailError("recipient_invalid")
    if not message.subject.strip():
        raise EmailError("subject_required")
    if not message.body_text.strip():
        raise EmailError("body_required")
    transport = (current_app.config.get("MAIL_TRANSPORT") or "smtp").lower()
    if transport == "memory":
        _deliver_memory(message)
        return
    if transport == "smtp":
        _deliver_smtp(message)
        return
    raise EmailError(f"unsupported_transport:{transport}")


def outbox() -> list:
    """Return the in-memory outbox for tests. Creates it lazily."""
    extensions = current_app.extensions
    box = extensions.get("_outbox")
    if box is None:
        box = []
        extensions["_outbox"] = box
    return box


def clear_outbox() -> None:
    """Discard every captured message. Only meaningful for the memory transport."""
    current_app.extensions["_outbox"] = []


def _deliver_memory(message: EmailMessage) -> None:
    box = outbox()
    box.append(message)


def _deliver_smtp(message: EmailMessage) -> None:
    server = current_app.config.get("MAIL_SERVER")
    port = int(current_app.config.get("MAIL_PORT") or 587)
    use_tls = bool(current_app.config.get("MAIL_USE_TLS"))
    username = current_app.config.get("MAIL_USERNAME")
    password = current_app.config.get("MAIL_PASSWORD")
    default_sender = current_app.config.get("MAIL_DEFAULT_SENDER")
    sender = message.sender or default_sender
    if not server or not sender:
        raise EmailError("smtp_not_configured")
    mime = _build_mime(message, sender)
    with smtplib.SMTP(server, port, timeout=30) as client:
        client.ehlo()
        if use_tls:
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if username and password:
            client.login(username, password)
        client.sendmail(sender, [message.to], mime.as_string())


def _build_mime(message: EmailMessage, sender: str) -> MIMEMultipart:
    if message.body_html:
        root = MIMEMultipart("alternative")
        root.attach(MIMEText(message.body_text, "plain", "utf-8"))
        root.attach(MIMEText(message.body_html, "html", "utf-8"))
    else:
        root = MIMEMultipart()
        root.attach(MIMEText(message.body_text, "plain", "utf-8"))
    root["From"] = sender
    root["To"] = message.to
    root["Subject"] = message.subject
    root["Date"] = formatdate(localtime=False)
    root["Message-ID"] = make_msgid(domain="trustseal.local")
    if message.reply_to:
        root["Reply-To"] = message.reply_to
    for key, value in message.headers.items():
        root[key] = value
    return root
