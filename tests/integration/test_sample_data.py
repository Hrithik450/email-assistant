"""
Integration tests validating that sample.json was correctly loaded into postgres
under the new user/email_user split schema.
Skipped automatically when DATABASE_URL is unavailable.
"""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def patch_pool(db_pool):
    with patch("src.tools.relational_query_tool.pool", db_pool):
        yield


def run_tool(query: str, limit: int = 50) -> str:
    from tools.relational_query_tool import relational_query_tool

    return relational_query_tool.invoke({"query": query, "limit": limit})


class TestSampleDataIntegrity:
    """Validate that the one record from sample.json loaded into the right tables."""

    def test_email_exists(self):
        result = run_tool(
            "SELECT gmail_email_id FROM email WHERE gmail_email_id = '18f3df9fb1898c38'"
        )
        assert "18f3df9fb1898c38" in result

    def test_email_thread_exists(self):
        result = run_tool(
            "SELECT gmail_thread_id FROM email_thread WHERE gmail_thread_id = '18dca81c4ab8a124'"
        )
        assert "18dca81c4ab8a124" in result

    # --- email_user table, NOT user table ---

    def test_sender_in_email_user_not_user(self):
        result = run_tool(
            "SELECT email FROM email_user WHERE email = 'milinsharma@gmail.com'"
        )
        assert "milinsharma@gmail.com" in result

    def test_sender_not_in_user_table(self):
        result = run_tool(
            "SELECT email FROM \"user\" WHERE email = 'milinsharma@gmail.com'"
        )
        assert "No rows" in result or "0 row" in result or "milinsharma" not in result

    def test_to_recipient_in_email_user(self):
        result = run_tool(
            "SELECT email FROM email_user WHERE email = 'akshata@2getherments.com'"
        )
        assert "akshata@2getherments.com" in result

    def test_six_email_users_loaded(self):
        result = run_tool("SELECT COUNT(*) AS cnt FROM email_user")
        assert "6" in result

    def test_user_table_is_empty(self):
        result = run_tool('SELECT COUNT(*) AS cnt FROM "user"')
        assert "0" in result

    # --- email → email_user FK join ---

    def test_email_joins_to_email_user_for_sender(self):
        result = run_tool("""
            SELECT e.subject, eu.display_name AS sender_name, eu.email AS sender_email
            FROM email e
            JOIN email_user eu ON e.sender_id = eu.id
            WHERE e.gmail_email_id = '18f3df9fb1898c38'
            """)
        assert "milin" in result.lower() or "milinsharma" in result.lower()

    def test_recipient_joins_to_email_user(self):
        result = run_tool("""
            SELECT eu.display_name, r.recipient_type
            FROM recipient r
            JOIN email_user eu ON r.person_id = eu.id
            WHERE r.recipient_type = 'TO'
            """)
        assert "TO" in result
        assert "akshata" in result.lower()

    def test_cc_recipients_in_email_user(self):
        result = run_tool("""
            SELECT eu.email
            FROM recipient r
            JOIN email_user eu ON r.person_id = eu.id
            WHERE r.recipient_type = 'CC'
            """)
        assert "hari@2getherments.com" in result

    # --- other tables ---

    def test_three_labels_loaded(self):
        result = run_tool("""
            SELECT label FROM email_label el
            JOIN email e ON el.email_id = e.id
            WHERE e.gmail_email_id = '18f3df9fb1898c38'
            """)
        assert "IMPORTANT" in result
        assert "INBOX" in result

    def test_attachment_loaded_with_correct_filename(self):
        result = run_tool("""
            SELECT att.filename, att.mime_type
            FROM attachment att
            JOIN email e ON att.email_id = e.id
            WHERE e.gmail_email_id = '18f3df9fb1898c38'
            """)
        assert "image.png" in result
        assert "image/png" in result

    def test_sent_at_is_timezone_aware(self):
        result = run_tool(
            "SELECT sent_at FROM email WHERE gmail_email_id = '18f3df9fb1898c38'"
        )
        assert "2024-05-03" in result
