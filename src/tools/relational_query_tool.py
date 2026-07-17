import re
from langchain.tools import tool

from src.lib.db import pool
from src.lib.logger import get_logger, log_tool_call

logger = get_logger(__name__)

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|COPY|EXECUTE|CALL|DO"
    r"|MERGE|VACUUM|COMMENT|PREPARE|LISTEN|NOTIFY|LOAD|REINDEX|CLUSTER|REFRESH|SET"
    r"|PG_READ_FILE|PG_READ_BINARY_FILE|PG_LS_DIR|PG_STAT_FILE"
    r"|LO_IMPORT|LO_EXPORT|LO_GET|LO_PUT|LO_UNLINK"
    r"|PG_SLEEP|DBLINK|PG_TERMINATE_BACKEND|PG_CANCEL_BACKEND)\b",
    re.IGNORECASE,
)

_ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

_HAS_SEMICOLON = re.compile(r";")

_MAX_ROWS = 100
_DEFAULT_ROWS = 20


def _validate_query(query: str) -> str | None:
    """Return an error string if the query is not safe, else None."""
    stripped = query.rstrip("; \n")
    if not _ALLOWED_START.match(stripped):
        return "Only SELECT or WITH (CTE) queries are allowed."
    if _HAS_SEMICOLON.search(stripped):
        return "Multiple statements (semicolons) are not allowed."
    if _FORBIDDEN.search(stripped):
        return "Query contains a forbidden keyword or function."
    return None


def _rows_to_markdown(columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return "_No rows returned._"
    header = " | ".join(columns)
    sep = " | ".join("---" for _ in columns)
    body = "\n".join(
        " | ".join(str(v) if v is not None else "NULL" for v in row) for row in rows
    )
    return f"| {header} |\n| {sep} |\n" + "\n".join(
        f"| {r} |" for r in body.splitlines()
    )


@tool("relational_query_tool", parse_docstring=True)
def relational_query_tool(query: str, limit: int = _DEFAULT_ROWS) -> str:
    """
    Execute a read-only SQL SELECT query on the email database.

    SCHEMA (PostgreSQL) — two separate user domains, never mix them:

    APPLICATION DOMAIN (authentication & chat):
    "user"          (id uuid PK, username varchar UNIQUE, email varchar UNIQUE, role varchar, created_at timestamptz)
    thread          (id uuid PK, user_id uuid FK→"user", title varchar, created_at timestamptz)
    thread_messages (id uuid PK, thread_id uuid FK→thread, role varchar[user|assistant], content text, created_at timestamptz)

    EMAIL DOMAIN (people extracted from imported emails only):
    email_user    (id uuid PK, display_name varchar, email varchar UNIQUE, domain varchar, created_at timestamptz)
    email_thread  (id uuid PK, gmail_thread_id varchar UNIQUE, subject text, first_email_at timestamptz, last_email_at timestamptz, message_count int, created_at timestamptz)
    email         (id uuid PK, gmail_email_id varchar UNIQUE, thread_id uuid FK→email_thread, sender_id uuid FK→email_user, subject text, snippet text, body text, sent_at timestamptz, created_at timestamptz)
    recipient     (id uuid PK, email_id uuid FK→email, person_id uuid FK→email_user, recipient_type varchar[TO|CC|BCC])
    attachment    (id uuid PK, email_id uuid FK→email, gmail_attachment_id varchar, filename varchar, mime_type varchar, size_bytes bigint)
    email_label   (id uuid PK, email_id uuid FK→email, label varchar)

    RELATIONSHIPS:
    - email.sender_id → email_user.id   (who sent the email)
    - recipient.person_id → email_user.id  (who received it; filter by recipient_type)
    - email.thread_id → email_thread.id (Gmail thread grouping)
    - thread.user_id → "user".id        (chat thread owner — app user, not email_user)

    TIPS:
    - Quote "user" in double-quotes (SQL reserved word). email_user needs no quoting.
    - Join email_user to resolve sender/recipient names and addresses.
    - Use email_label to filter by label (INBOX, IMPORTANT, CATEGORY_PERSONAL, …).
    - Only SELECT / WITH (CTEs) are permitted. Any DML/DDL raises an error.

    Args:
        query: A SQL SELECT (or WITH …) query to execute. No semicolons required.
        limit: Maximum rows to return (default 20, hard cap 100).
    """
    log_tool_call("relational_query_tool", query)
    err = _validate_query(query)
    if err:
        return f"Query rejected: {err}"

    limit = max(1, min(limit, _MAX_ROWS))

    safe_query = f"SELECT * FROM ({query.rstrip('; \n')}) _q LIMIT {limit}"

    try:
        with pool.connection() as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                with conn.cursor() as cur:
                    cur.execute(safe_query)
                    rows = cur.fetchall()
                    columns = (
                        [desc[0] for desc in cur.description] if cur.description else []
                    )
    except Exception as exc:
        logger.warning("sql_query_tool error: %s", exc)
        return "Query error: the query could not be executed. Check syntax and table/column names."

    total = len(rows)
    table = _rows_to_markdown(columns, rows)
    note = f"\n\n_Showing {total} row(s) (limit={limit})._"
    return table + note
