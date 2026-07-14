import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from src.lib.db import pool

load_dotenv(override=True)

NORM_DATA = Path(__file__).parent.parent / "src" / "lib" / "data" / "norm_data.jsonl"
DATABASE_URL = os.environ["DATABASE_URL"]

BATCH_SIZE = 500


def parse_ts(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def ensure_email_user(cur, display_name: str, email: str, domain: str) -> str:
    cur.execute(
        """
        INSERT INTO email_user (id, display_name, email, domain)
        VALUES (gen_random_uuid(), %s, %s, %s)
        ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
        RETURNING id
        """,
        (display_name or "", email, domain or ""),
    )
    return str(cur.fetchone()[0])


def ensure_email_thread(cur, gmail_thread_id: str, subject: str | None) -> str:
    cur.execute(
        """
        INSERT INTO email_thread (id, gmail_thread_id, subject)
        VALUES (gen_random_uuid(), %s, %s)
        ON CONFLICT (gmail_thread_id)
        DO UPDATE SET subject = COALESCE(EXCLUDED.subject, email_thread.subject)
        RETURNING id
        """,
        (gmail_thread_id, subject),
    )
    return str(cur.fetchone()[0])


def ingest_record(cur, rec: dict) -> None:
    frm = rec.get("from") or {}
    sender_id = ensure_email_user(
        cur,
        frm.get("name", ""),
        frm.get("email", "unknown@unknown.com"),
        frm.get("domain", ""),
    )

    thread_uuid = ensure_email_thread(cur, rec["threadId"], rec.get("subject"))

    sent_at = parse_ts(rec.get("date"))
    body_raw = rec.get("body", "")
    body_text = body_raw if isinstance(body_raw, str) else ""

    cur.execute(
        """
        INSERT INTO email (id, gmail_email_id, thread_id, sender_id, subject, snippet, body, sent_at)
        VALUES (gen_random_uuid(), %s, %s::uuid, %s::uuid, %s, %s, %s, %s)
        ON CONFLICT (gmail_email_id) DO NOTHING
        RETURNING id
        """,
        (
            rec["id"],
            thread_uuid,
            sender_id,
            rec.get("subject"),
            rec.get("snippet"),
            body_text,
            sent_at,
        ),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute("SELECT id FROM email WHERE gmail_email_id = %s", (rec["id"],))
        row = cur.fetchone()
    email_uuid = str(row[0])

    for rtype, field in [("TO", "to"), ("CC", "cc"), ("BCC", "bcc")]:
        people = rec.get(field) or []
        if isinstance(people, dict):
            people = [people]
        for p in people:
            if not p or not p.get("email"):
                continue
            person_id = ensure_email_user(
                cur, p.get("name", ""), p["email"], p.get("domain", "")
            )
            cur.execute(
                """
                INSERT INTO recipient (id, email_id, person_id, recipient_type)
                VALUES (gen_random_uuid(), %s::uuid, %s::uuid, %s)
                ON CONFLICT DO NOTHING
                """,
                (email_uuid, person_id, rtype),
            )

    for att in rec.get("attachments") or []:
        cur.execute(
            """
            INSERT INTO attachment (id, email_id, gmail_attachment_id, filename, mime_type, size_bytes)
            VALUES (gen_random_uuid(), %s::uuid, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                email_uuid,
                att.get("attachmentId", ""),
                att.get("filename"),
                att.get("mimeType"),
                att.get("sizeBytes"),
            ),
        )

    for lbl in rec.get("labels") or []:
        cur.execute(
            """
            INSERT INTO email_label (id, email_id, label)
            VALUES (gen_random_uuid(), %s::uuid, %s)
            ON CONFLICT DO NOTHING
            """,
            (email_uuid, lbl),
        )


def commit_batch(
    conn,
    batch: list[dict],
) -> tuple[int, int]:
    """Insert one batch in a single transaction. Returns (inserted, skipped).

    Uses savepoints so a bad individual record rolls back only itself without
    losing the other records already inserted in this batch.
    """
    inserted = skipped = 0
    with conn.cursor() as cur:
        for rec in batch:
            cur.execute("SAVEPOINT sp")
            try:
                ingest_record(cur, rec)
                cur.execute("RELEASE SAVEPOINT sp")
                inserted += 1
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                print(f"    [skip] email {rec.get('id', '?')}: {exc}", file=sys.stderr)
                skipped += 1
        conn.commit()
    return inserted, skipped


def migrate(path: Path = NORM_DATA, batch_size: int = BATCH_SIZE) -> None:
    if not path.exists():
        sys.exit(f"File not found: {path}")

    print(f"Source : {path}")
    print(f"Batch  : {batch_size} records per transaction")
    print(f"DSN    : {DATABASE_URL[:40]}...")
    print()

    total_inserted = total_skipped = total_lines = 0
    batch: list[dict] = []
    batch_num = 0

    with pool.connection() as conn:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                total_lines += 1

                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(f"[bad json] line {lineno}: {exc}", file=sys.stderr)
                    total_skipped += 1
                    continue

                if not rec.get("id") or not rec.get("threadId"):
                    print(
                        f"[missing id/threadId] line {lineno} — skipped",
                        file=sys.stderr,
                    )
                    total_skipped += 1
                    continue

                batch.append(rec)

                if len(batch) >= batch_size:
                    batch_num += 1
                    ins, skp = commit_batch(conn, batch, batch_num, total_inserted)
                    total_inserted += ins
                    total_skipped += skp
                    print(
                        f"  Batch {batch_num:4d} | committed {ins:4d} | running total {total_inserted:6d} | skipped {total_skipped}"
                    )
                    batch.clear()

        if batch:
            batch_num += 1
            ins, skp = commit_batch(conn, batch, batch_num, total_inserted)
            total_inserted += ins
            total_skipped += skp
            print(
                f"  Batch {batch_num:4d} | committed {ins:4d} | running total {total_inserted:6d} | skipped {total_skipped}"
            )

    print(
        f"Done. Lines read: {total_lines} | Inserted: {total_inserted} | Skipped: {total_skipped}"
    )


if __name__ == "__main__":
    migrate()
