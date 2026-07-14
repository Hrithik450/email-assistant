"""Unit tests for SQLAlchemy model definitions — no DB connection required."""

import pytest
from sqlalchemy import inspect as sa_inspect

from src.models.models import (
    User,
    EmailUser,
    ConversationThread,
    ConversationMessage,
    EmailThread,
    Email,
    Recipient,
    Attachment,
    EmailLabel,
    Base,
)


# ---------------------------------------------------------------------------
# Table names
# ---------------------------------------------------------------------------

class TestTableNames:
    def test_user_tablename(self):
        assert User.__tablename__ == "user"

    def test_email_user_tablename(self):
        assert EmailUser.__tablename__ == "email_user"

    def test_conversation_thread_tablename(self):
        assert ConversationThread.__tablename__ == "thread"

    def test_conversation_message_tablename(self):
        assert ConversationMessage.__tablename__ == "thread_messages"

    def test_email_thread_tablename(self):
        assert EmailThread.__tablename__ == "email_thread"

    def test_email_tablename(self):
        assert Email.__tablename__ == "email"

    def test_recipient_tablename(self):
        assert Recipient.__tablename__ == "recipient"

    def test_attachment_tablename(self):
        assert Attachment.__tablename__ == "attachment"

    def test_email_label_tablename(self):
        assert EmailLabel.__tablename__ == "email_label"


# ---------------------------------------------------------------------------
# No duplicate models
# ---------------------------------------------------------------------------

class TestNoDuplicateModels:
    def test_all_tables_unique(self):
        tables = [m.__tablename__ for m in Base.__subclasses__()]
        assert len(tables) == len(set(tables)), f"Duplicate tablenames: {tables}"


# ---------------------------------------------------------------------------
# User domain — app auth only
# ---------------------------------------------------------------------------

class TestUserModel:
    def _cols(self, model):
        return {c.name for c in model.__table__.columns}

    def test_user_has_username(self):
        assert "username" in self._cols(User)

    def test_user_has_role(self):
        assert "role" in self._cols(User)

    def test_user_has_no_domain(self):
        assert "domain" not in self._cols(User)

    def test_user_has_no_display_name(self):
        assert "display_name" not in self._cols(User)

    def test_user_has_no_user_name(self):
        assert "user_name" not in self._cols(User)

    def test_user_relationships(self):
        rel_names = {r.key for r in sa_inspect(User).relationships}
        assert "conversation_threads" in rel_names
        # user must NOT have email-domain relationships
        assert "sent_emails" not in rel_names
        assert "recipients" not in rel_names


# ---------------------------------------------------------------------------
# EmailUser domain — email participants only
# ---------------------------------------------------------------------------

class TestEmailUserModel:
    def _cols(self, model):
        return {c.name for c in model.__table__.columns}

    def test_email_user_has_display_name(self):
        assert "display_name" in self._cols(EmailUser)

    def test_email_user_has_domain(self):
        assert "domain" in self._cols(EmailUser)

    def test_email_user_has_no_username(self):
        assert "username" not in self._cols(EmailUser)

    def test_email_user_has_no_role(self):
        assert "role" not in self._cols(EmailUser)

    def test_email_user_relationships(self):
        rel_names = {r.key for r in sa_inspect(EmailUser).relationships}
        assert "sent_emails" in rel_names
        assert "received_emails" in rel_names

    def test_domains_are_separate(self):
        """User and EmailUser must be different tables — never merged."""
        assert User.__tablename__ != EmailUser.__tablename__


# ---------------------------------------------------------------------------
# Foreign key correctness — email domain must reference email_user, NOT user
# ---------------------------------------------------------------------------

class TestForeignKeys:
    def _fk_targets(self, model, col_name) -> set[str]:
        cols = {c.name: c for c in model.__table__.columns}
        return {fk.column.table.name for fk in cols[col_name].foreign_keys}

    def test_email_sender_fk_points_to_email_user(self):
        targets = self._fk_targets(Email, "sender_id")
        assert "email_user" in targets
        assert "user" not in targets

    def test_recipient_person_fk_points_to_email_user(self):
        targets = self._fk_targets(Recipient, "person_id")
        assert "email_user" in targets
        assert "user" not in targets

    def test_thread_user_fk_points_to_user(self):
        targets = self._fk_targets(ConversationThread, "user_id")
        assert "user" in targets
        assert "email_user" not in targets

    def test_thread_messages_fk_points_to_thread(self):
        targets = self._fk_targets(ConversationMessage, "thread_id")
        assert "thread" in targets

    def test_email_thread_fk_points_to_email_thread(self):
        targets = self._fk_targets(Email, "thread_id")
        assert "email_thread" in targets


# ---------------------------------------------------------------------------
# Column presence
# ---------------------------------------------------------------------------

class TestColumnPresence:
    def _cols(self, model):
        return {c.name for c in model.__table__.columns}

    def test_conversation_message_has_content_not_message(self):
        cols = self._cols(ConversationMessage)
        assert "content" in cols
        assert "message" not in cols

    def test_thread_has_title_and_user_id(self):
        cols = self._cols(ConversationThread)
        assert "title" in cols
        assert "user_id" in cols
