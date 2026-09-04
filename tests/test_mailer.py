"""Email over your own SMTP/IMAP, offline.

The SMTP and IMAP clients are injected, so sending, reply parsing and choice
resolution are verified without a mail server.
"""
from conductor.mailer import (InboxReader, Mailer, decision_email, reader_from_env,
                              resolve_choice)


def test_decision_email_carries_id_and_numbered_options():
    subject, body = decision_email({"id": "dec_9", "question": "Paywall?", "options": ["after value", "on signup"]})
    assert subject.startswith("[Conductor dec_9]")
    assert "1. after value" in body and "2. on signup" in body
    assert "Reply with the number" in body


def test_resolve_choice_by_number_and_by_text():
    opts = ["after value", "on signup", "usage limit"]
    assert resolve_choice("2", opts) == "on signup"
    assert resolve_choice("1. after value", opts) == "after value"
    assert resolve_choice("on signup", opts) == "on signup"
    assert resolve_choice("I think the usage limit one", opts) == "usage limit"
    assert resolve_choice("", opts) is None
    assert resolve_choice("99", opts) is None


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.did = []
        self.sent = None
        FakeSMTP.instances.append(self)

    def starttls(self): self.did.append("starttls")
    def login(self, u, p): self.did.append(("login", u))
    def send_message(self, msg): self.sent = msg
    def quit(self): self.did.append("quit")


def test_mailer_sends_over_injected_smtp():
    FakeSMTP.instances.clear()
    m = Mailer(host="smtp.acme.co", port=587, user="bot@acme.co", password="pw",
               sender="conductor@acme.co", smtp_factory=FakeSMTP)
    m.send("alex@acme.co", "[Conductor dec_1] Q?", "body here")
    s = FakeSMTP.instances[0]
    assert "starttls" in s.did and ("login", "bot@acme.co") in s.did
    assert s.sent["To"] == "alex@acme.co" and s.sent["From"] == "conductor@acme.co"
    assert s.sent["Subject"] == "[Conductor dec_1] Q?"


def test_mailer_ssl_skips_starttls():
    FakeSMTP.instances.clear()
    m = Mailer(host="h", port=465, user="u", password="p", sender="s",
               ssl=True, starttls=True, smtp_factory=FakeSMTP)
    m.send("a@b.co", "subj", "body")
    assert "starttls" not in FakeSMTP.instances[0].did   # 465 is already encrypted


def test_mailer_from_env_infers_ssl_on_465(monkeypatch):
    from conductor.mailer import mailer_from_env
    monkeypatch.setenv("CONDUCTOR_SMTP_HOST", "server372.web-hosting.com")
    monkeypatch.setenv("CONDUCTOR_SMTP_FROM", "conductor@rolepilotai.com")
    monkeypatch.setenv("CONDUCTOR_SMTP_PORT", "465")
    m = mailer_from_env()
    assert m.ssl is True and m.starttls is False and m.port == 465


class FakeIMAP:
    def __init__(self, messages):
        self._messages = messages     # {num: raw_bytes}
        self.stored = []

    def login(self, u, p): pass
    def select(self, box): return ("OK", [b"1"])
    def search(self, charset, *criteria):
        return ("OK", [b" ".join(k.encode() for k in self._messages)])
    def fetch(self, num, spec):
        return ("OK", [(num, self._messages[num.decode()])])
    def store(self, num, flags, value): self.stored.append((num, value))
    def logout(self): pass


def _raw(subject, body):
    return (f"Subject: {subject}\r\nFrom: alex@acme.co\r\n\r\n{body}\r\n").encode()


def test_inbox_reader_extracts_decision_and_marks_seen():
    msgs = {
        "1": _raw("Re: [Conductor dec_7] Paywall?", "2\n\nOn Tue, Conductor wrote:\n> pick one"),
        "2": _raw("Some unrelated email", "hello"),
    }
    reader = InboxReader(host="imap.acme.co", port=993, user="bot@acme.co", password="pw",
                         imap_factory=lambda h, p: FakeIMAP(msgs))
    replies = reader.poll()
    assert replies == [("dec_7", "2")]                # only the tagged one, first line only


def test_from_env_requires_config(monkeypatch):
    for k in ("CONDUCTOR_SMTP_HOST", "CONDUCTOR_SMTP_FROM", "CONDUCTOR_SMTP_USER",
              "CONDUCTOR_IMAP_HOST", "CONDUCTOR_IMAP_USER"):
        monkeypatch.delenv(k, raising=False)
    assert reader_from_env() is None
    monkeypatch.setenv("CONDUCTOR_IMAP_HOST", "imap.acme.co")
    monkeypatch.setenv("CONDUCTOR_IMAP_USER", "bot@acme.co")
    assert reader_from_env() is not None
