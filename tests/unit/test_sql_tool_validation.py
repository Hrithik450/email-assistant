"""Unit tests for SQL tool query validation — no DB required."""

import pytest
from tools.relational_query_tool import _validate_query


class TestValidateQuery:
    # --- allowed ---
    def test_select_allowed(self):
        assert _validate_query("SELECT * FROM email") is None

    def test_with_cte_allowed(self):
        assert (
            _validate_query("WITH cte AS (SELECT id FROM email) SELECT * FROM cte")
            is None
        )

    def test_select_with_join(self):
        q = 'SELECT e.subject, u.email FROM email e JOIN "user" u ON e.sender_id = u.id'
        assert _validate_query(q) is None

    def test_select_with_where(self):
        assert (
            _validate_query("SELECT * FROM email WHERE sent_at > '2024-01-01'") is None
        )

    def test_select_case_insensitive(self):
        assert _validate_query("select id from email_label") is None

    # --- rejected: wrong start ---
    def test_insert_rejected(self):
        assert _validate_query("INSERT INTO email (subject) VALUES ('x')") is not None

    def test_update_rejected(self):
        assert _validate_query("UPDATE email SET subject='hack'") is not None

    def test_delete_rejected(self):
        assert _validate_query("DELETE FROM email WHERE id='1'") is not None

    def test_drop_rejected(self):
        assert _validate_query("DROP TABLE email") is not None

    def test_create_rejected(self):
        assert _validate_query("CREATE TABLE evil (id int)") is not None

    def test_alter_rejected(self):
        assert _validate_query("ALTER TABLE email ADD COLUMN x text") is not None

    def test_truncate_rejected(self):
        assert _validate_query("TRUNCATE email") is not None

    # --- rejected: forbidden keyword embedded in SELECT ---
    def test_select_with_embedded_delete_rejected(self):
        # Attempt SQL injection via subquery
        assert _validate_query("SELECT * FROM email; DELETE FROM email") is not None

    def test_select_with_drop_comment_rejected(self):
        q = "SELECT 1; DROP TABLE email --"
        assert _validate_query(q) is not None
