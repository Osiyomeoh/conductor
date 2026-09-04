"""Email delivery over your own SMTP/IMAP, no third-party service.

Send: a decision (or a digest) goes out over SMTP with the decision id in the
subject. Reply: the person answers by replying to that email; a poll over IMAP
reads unseen replies, pulls the decision id back out of the subject and the
choice from the first line, and answers. It mirrors the Slack path for people
who live in their inbox.

The SMTP and IMAP client factories are injectable, so message building, sending
and reply parsing are all unit-tested without a mail server.
"""

from __future__ import annotations

import email
import os
import re
from dataclasses import dataclass
from email.message import EmailMessage

_TAG = re.compile(r"\[Conductor (dec_[A-Za-z0-9]+)\]")


def decision_email(d: dict) -> tuple[str, str]:
    """Subject (carrying the decision id) and plain-text body for one decision."""
    subject = f"[Conductor {d['id']}] {d.get('question', 'A decision needs you')}"[:180]
    lines = [d.get("question", ""), ""]
    for i, o in enumerate(d.get("options", []), 1):
        lines.append(f"  {i}. {o}")
    lines += ["", "Reply with the number (e.g. 1) or the exact option text to answer.",
              "Everything else was already handled."]
    return subject, "\n".join(lines)


def resolve_choice(reply_text: str, options: list[str]) -> str | None:
    """Map a reply to an option: a leading number picks by position, otherwise
    match the option text (case-insensitive, exact or contained)."""
    text = (reply_text or "").strip()
    if not text or not options:
        return None
    m = re.match(r"\s*(\d+)", text)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(options):
            return options[idx]
    low = text.lower()
    for o in options:
        if o.lower() == low:
            return o
    for o in options:
        if o.lower() in low or low in o.lower():
            return o
    return None


@dataclass
class Mailer:
    host: str
    port: int
    user: str
    password: str
    sender: str
    starttls: bool = True
    smtp_factory: object = None      # (host, port) -> smtp client; injectable for tests

    def send(self, to: str, subject: str, body: str) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        make = self.smtp_factory or (lambda h, p: __import__("smtplib").SMTP(h, p, timeout=20))
        smtp = make(self.host, self.port)
        try:
            if self.starttls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:  # noqa: BLE001
                pass
        return msg


def _first_line(msg) -> str:
    """The first non-empty, non-quoted line of a reply's plain text."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors="replace")
                break
    else:
        body = (msg.get_payload(decode=True) or b"").decode(errors="replace")
    for ln in body.splitlines():
        s = ln.strip()
        if s and not s.startswith(">") and not s.lower().startswith("on "):
            return s
    return ""


@dataclass
class InboxReader:
    host: str
    port: int
    user: str
    password: str
    imap_factory: object = None      # (host, port) -> imap client; injectable for tests

    def poll(self) -> list[tuple[str, str]]:
        """Unseen replies as (decision_id, reply_text). Marks them seen so a
        reply is acted on once."""
        make = self.imap_factory or (lambda h, p: __import__("imaplib").IMAP4_SSL(h, p))
        imap = make(self.host, self.port)
        out: list[tuple[str, str]] = []
        try:
            imap.login(self.user, self.password)
            imap.select("INBOX")
            _typ, data = imap.search(None, "UNSEEN")
            for num in (data[0].split() if data and data[0] else []):
                _t, msgdata = imap.fetch(num, "(RFC822)")
                raw = msgdata[0][1]
                msg = email.message_from_bytes(raw)
                m = _TAG.search(msg.get("Subject", ""))
                if not m:
                    continue
                out.append((m.group(1), _first_line(msg)))
                imap.store(num, "+FLAGS", "\\Seen")
        finally:
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass
        return out


def mailer_from_env() -> Mailer | None:
    host = os.environ.get("CONDUCTOR_SMTP_HOST")
    sender = os.environ.get("CONDUCTOR_SMTP_FROM") or os.environ.get("CONDUCTOR_SMTP_USER")
    if not host or not sender:
        return None
    return Mailer(host=host, port=int(os.environ.get("CONDUCTOR_SMTP_PORT", "587")),
                  user=os.environ.get("CONDUCTOR_SMTP_USER", ""),
                  password=os.environ.get("CONDUCTOR_SMTP_PASSWORD", ""),
                  sender=sender,
                  starttls=os.environ.get("CONDUCTOR_SMTP_STARTTLS", "1") == "1")


def reader_from_env() -> InboxReader | None:
    host = os.environ.get("CONDUCTOR_IMAP_HOST")
    user = os.environ.get("CONDUCTOR_IMAP_USER")
    if not host or not user:
        return None
    return InboxReader(host=host, port=int(os.environ.get("CONDUCTOR_IMAP_PORT", "993")),
                       user=user, password=os.environ.get("CONDUCTOR_IMAP_PASSWORD", ""))
