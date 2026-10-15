"""The daily moderation digest: rendering (backend.helpers.submission_digest) and sending
(backend.prefect.submission_digest_pipeline)."""

import logging

import pytest

import backend.prefect.submission_digest_pipeline as pipeline
from backend.helpers.submission_digest import DigestItem, about, build_digest, summary, type_label

SITE = "https://mshsfootball.com/"


def _score(status: str = "pending", **payload) -> DigestItem:
    """A score correction for Oxford on Oct 10 with Tupelo on the site at 14–16."""
    return DigestItem(
        id=7,
        type="score",
        status=status,
        school="Oxford",
        payload={"date": "2026-10-10", "points_for": 21, "points_against": 16, **payload},
        current_game={"opponent": "Tupelo", "points_for": 14, "points_against": 16},
    )


def _feedback(**payload) -> DigestItem:
    """An odds report from a region page."""
    return DigestItem(
        id=8,
        type="feedback",
        status="pending",
        school=None,
        payload={
            "subject": "Odds or scenarios · Region 2-7A · Oxford",
            "message": "Oxford can't\n\n be 4th",
            "category": "odds",
            **payload,
        },
    )


class TestSummary:
    """One line per submission."""

    def test_score_shows_reported_and_current(self):
        """Reported score, the site's score, and the source."""
        line = summary(_score(note="MaxPreps box score"))
        assert line == "Oxford vs Tupelo, Sat Oct 10: reported 21–16 (site shows 14–16). Source: MaxPreps box score"

    def test_score_without_a_game_row(self):
        """No live game: says so instead of a score."""
        item = DigestItem(7, "score", "pending", "Oxford", {"date": "2026-10-10", "points_for": 1, "points_against": 0})
        assert summary(item).endswith("reported 1–0 (no game on the site that day)")

    def test_feedback_drops_the_category_from_the_subject(self):
        """The label carries the category; the line carries what it's about and the message, flattened."""
        assert type_label(_feedback()) == "Feedback · Odds or scenarios"
        assert summary(_feedback()) == "Region 2-7A · Oxford: Oxford can't be 4th"

    def test_feedback_with_only_a_category_subject(self):
        """A subject that is only the category leaves just the message."""
        item = _feedback(subject="Feedback", category="other")
        assert about(item) == ""
        assert summary(item) == "Oxford can't be 4th"

    def test_long_messages_are_clipped(self):
        """Messages are cut to a preview."""
        assert summary(_feedback(message="x" * 1000)).endswith("…")

    def test_other_types(self):
        """Other types show their label and school."""
        item = DigestItem(9, "helmet_assignment", "pending", "Tupelo", {})
        assert (type_label(item), summary(item)) == ("Helmet worn", "Tupelo")


class TestBuildDigest:
    """The email as a whole."""

    def test_subject_and_counts(self):
        """Subject carries only counts; the header breaks pending down by type."""
        email = build_digest([_score(), _feedback()], {"score": 3, "feedback": 1, "logo": 0}, SITE)
        assert email.subject == "Moderation: 2 new submissions, 4 pending"
        assert email.text.startswith(
            "2 new submissions in the last day. 4 pending in all (1 feedback, 3 score correction)."
        )
        assert "https://mshsfootball.com/moderate" in email.text

    def test_visitor_text_is_escaped_in_html(self):
        """Anything a visitor typed is escaped in the HTML part."""
        email = build_digest([_feedback(message="<script>alert(1)</script>", email="a@b.co")], {"feedback": 1}, SITE)
        assert "<script>" not in email.html
        assert "&lt;script&gt;" in email.html
        assert "Reply to: a@b.co" in email.text

    def test_reviewed_items_are_marked(self):
        """Something already handled says so."""
        email = build_digest([_score(status="approved")], {}, SITE, hours=48)
        assert "#7 Score correction [approved]" in email.text
        assert "1 new submission in the last 48 hours. 0 pending in all." in email.text


class FakeSMTP:
    """Records what the pipeline does with an SMTP connection."""

    instances: list = []

    def __init__(self, host, port, **kw):
        """Remember where it connected."""
        self.host, self.port, self.kw, self.actions = host, port, kw, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *exc):
        """Context manager exit."""
        return False

    def starttls(self, context=None):
        """Record STARTTLS."""
        self.actions.append("starttls")

    def login(self, user, password):
        """Record the login."""
        self.actions.append(("login", user))

    def send_message(self, message):
        """Record the message."""
        self.actions.append(("send", message["To"], message["Subject"]))


@pytest.fixture
def smtp_env(monkeypatch):
    """A STARTTLS server with a login and two recipients."""
    for key, value in {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_USERNAME": "bot@example.com",
        "SMTP_PASSWORD": "pw",
        "DIGEST_TO": "a@example.com, b@example.com",
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("SMTP_PORT", "SMTP_SECURITY", "SMTP_FROM"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(pipeline, "get_run_logger", lambda: logging.getLogger("test"))
    FakeSMTP.instances = []


class TestSending:
    """SMTP settings and delivery."""

    def test_settings_default_to_starttls_on_587(self, smtp_env):
        """Defaults: port 587, STARTTLS, From = the login."""
        settings = pipeline.smtp_settings()
        assert (settings["port"], settings["security"], settings["sender"]) == (587, "starttls", "bot@example.com")
        assert settings["recipients"] == ["a@example.com", "b@example.com"]

    def test_port_465_means_ssl(self, smtp_env, monkeypatch):
        """Port 465 implies implicit TLS."""
        monkeypatch.setenv("SMTP_PORT", "465")
        assert pipeline.smtp_settings()["security"] == "ssl"

    def test_unconfigured_sends_nothing(self, smtp_env, monkeypatch):
        """No host: the digest is logged, not sent."""
        monkeypatch.delenv("SMTP_HOST")
        assert pipeline.smtp_settings() is None
        assert pipeline.send_digest.fn(build_digest([_score()], {}, SITE)) is False

    def test_sends_over_starttls_with_login(self, smtp_env, monkeypatch):
        """STARTTLS, login, then one message to every recipient."""
        monkeypatch.setattr(pipeline.smtplib, "SMTP", FakeSMTP)
        assert pipeline.send_digest.fn(build_digest([_score()], {"score": 1}, SITE)) is True
        (server,) = FakeSMTP.instances
        assert server.actions == [
            "starttls",
            ("login", "bot@example.com"),
            ("send", "a@example.com, b@example.com", "Moderation: 1 new submission, 1 pending"),
        ]

    def test_ssl_uses_smtp_ssl(self, smtp_env, monkeypatch):
        """Implicit TLS connects with SMTP_SSL and skips STARTTLS."""
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setattr(pipeline.smtplib, "SMTP_SSL", FakeSMTP)
        pipeline.send_digest.fn(build_digest([_score()], {}, SITE))
        assert "starttls" not in FakeSMTP.instances[0].actions

    def test_message_has_text_and_html(self):
        """Multipart: the plain text first, then HTML."""
        message = pipeline.build_message(build_digest([_feedback()], {}, SITE), "bot@example.com", ["a@example.com"])
        assert [p.get_content_type() for p in message.iter_parts()] == ["text/plain", "text/html"]

    def test_row_to_item(self):
        """A query row with no game match has no current_game."""
        item = pipeline.row_to_item((3, "feedback", "pending", None, None, False, None, None, None))
        assert (item.payload, item.current_game) == ({}, None)


class TestFlow:
    """The flow sends only when something new still needs a decision."""

    def test_quiet_day_sends_nothing(self, smtp_env, monkeypatch):
        """No new submissions: no email."""
        monkeypatch.setattr(pipeline, "load_new_submissions", lambda hours: ([], {"score": 2}))
        monkeypatch.setattr(pipeline, "send_digest", lambda d: pytest.fail("should not send"))
        assert pipeline.submission_digest_flow.fn() == 0

    def test_new_submissions_are_sent(self, smtp_env, monkeypatch):
        """New submissions: one digest."""
        sent = []
        monkeypatch.setattr(pipeline, "load_new_submissions", lambda hours: ([_score(), _feedback()], {"score": 1}))
        monkeypatch.setattr(pipeline, "send_digest", sent.append)
        assert pipeline.submission_digest_flow.fn() == 2
        assert sent[0].subject == "Moderation: 2 new submissions, 1 pending"

    def test_already_handled_sends_nothing(self, smtp_env, monkeypatch):
        """New submissions that were all reviewed already: no email."""
        monkeypatch.setattr(
            pipeline, "load_new_submissions", lambda hours: ([_score(status="approved"), _score(status="rejected")], {})
        )
        monkeypatch.setattr(pipeline, "send_digest", lambda d: pytest.fail("should not send"))
        assert pipeline.submission_digest_flow.fn() == 0

    def test_only_waiting_items_are_listed(self, smtp_env, monkeypatch):
        """Handled ones are left out; a logo awaiting its asset still counts as waiting."""
        sent = []
        logo = DigestItem(9, "logo", "accepted_pending_asset", "Tupelo", {})
        monkeypatch.setattr(
            pipeline,
            "load_new_submissions",
            lambda hours: ([_score(status="approved"), _feedback(), logo], {"feedback": 1}),
        )
        monkeypatch.setattr(pipeline, "send_digest", sent.append)
        assert pipeline.submission_digest_flow.fn() == 2
        assert "#7" not in sent[0].text
        assert "#8 Feedback" in sent[0].text and "#9 Logo [accepted pending asset]" in sent[0].text
