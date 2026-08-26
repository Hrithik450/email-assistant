"""
Integration tests for sql_query_tool — requires a running postgres with sample data loaded.
Skipped automatically when DATABASE_URL is not available or postgres is unreachable.
"""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def patch_pool(db_pool):
    """Replace src.lib.db.pool with the test pool for all tests in this module."""
    with patch("src.tools.relational_query_tool.pool", db_pool):
        yield


def run_tool(query: str, limit: int = 20) -> str:
    from src.tools.relational_query_tool import relational_query_tool

    return relational_query_tool.invoke({"query": query, "limit": limit})


class TestSqlToolLive:
    def test_select_all_email_users(self):
        result = run_tool("SELECT id, display_name, email FROM email_user")
        assert "display_name" in result or "email" in result
        assert "milin" in result.lower() or "@" in result

    def test_select_emails(self):
        result = run_tool("SELECT gmail_email_id, subject, snippet FROM email LIMIT 5")
        assert "18f3df9fb1898c38" in result or "subject" in result

    def test_join_email_with_sender_via_email_user(self):
        result = run_tool("""
            SELECT e.subject, eu.display_name AS sender_name, eu.email AS sender_email
            FROM email e
            JOIN email_user eu ON e.sender_id = eu.id
            LIMIT 5
            """)
        assert "sender_name" in result or "milin" in result.lower()

    def test_email_labels(self):
        result = run_tool("SELECT label FROM email_label")
        assert "INBOX" in result or "IMPORTANT" in result or "label" in result

    def test_attachment_query(self):
        result = run_tool("SELECT filename, mime_type, size_bytes FROM attachment")
        assert "image.png" in result or "filename" in result

    def test_limit_respected(self):
        result = run_tool("SELECT * FROM email_user", limit=2)
        assert "_Showing" in result
        lines = [l for l in result.splitlines() if l.startswith("|") and "---" not in l]
        assert len(lines) <= 3

    def test_write_rejected(self):
        result = run_tool("DELETE FROM email WHERE id='fake'")
        assert "rejected" in result.lower()

    def test_update_rejected(self):
        result = run_tool("UPDATE email SET subject='hack'")
        assert "rejected" in result.lower()

    def test_empty_result(self):
        result = run_tool(
            "SELECT * FROM email WHERE subject = 'this_subject_does_not_exist_xyz'"
        )
        assert "No rows" in result or "0 row" in result

    def test_cte_works(self):
        result = run_tool("""
            WITH senders AS (
                SELECT DISTINCT sender_id FROM email
            )
            SELECT eu.display_name, eu.email
            FROM senders s
            JOIN email_user eu ON s.sender_id = eu.id
            """)
        assert "display_name" in result or "email" in result

    def test_user_table_is_empty(self):
        result = run_tool('SELECT COUNT(*) AS cnt FROM "user"')
        assert "0" in result


class TestRecipientQueries:
    def test_to_recipients_via_email_user(self):
        result = run_tool("""
            SELECT eu.display_name, eu.email, r.recipient_type
            FROM recipient r
            JOIN email_user eu ON r.person_id = eu.id
            WHERE r.recipient_type = 'TO'
            """)
        assert "TO" in result or "akshata" in result.lower()

    def test_cc_recipients_via_email_user(self):
        result = run_tool("""
            SELECT eu.display_name, r.recipient_type
            FROM recipient r
            JOIN email_user eu ON r.person_id = eu.id
            WHERE r.recipient_type = 'CC'
            """)
        assert "CC" in result
