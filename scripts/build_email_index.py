"""
build_email_index.py — Full email re-indexer for pgvector.

Reads every email directly from Postgres, chunks at 800 tokens (1 email → 1+
chunks, never merges multiple emails), embeds with Gemini gemini-embedding-001
(3072-d), and upserts into email_embedding.

Key-pool behaviour
──────────────────
• Round-robins across all keys in GEMINI_KEYS env vars.
• On any 429 / RESOURCE_EXHAUSTED → marks that key on a 120-second cooldown,
  switches to the next ready key immediately (no sleep on the calling thread).
• If every key is cooling down → waits for the soonest-available key.
• Idempotent / resumable: rows whose source_id already exist are skipped, so
  re-running after a crash continues exactly where it left off.
• Pass --truncate to wipe email_embedding and do a clean rebuild.

Usage
─────
    uv run python scripts/build_email_index.py            # full build
    uv run python scripts/build_email_index.py --dry-run  # count chunks only
    uv run python scripts/build_email_index.py --truncate # wipe + rebuild

Storage estimate (printed at end of every run)
────────────────────────────────────────────────
    3072 float32 × 4 bytes = 12 288 bytes ≈ 12 KB per vector (raw).
    HNSW index (halfvec, m=16, ef=64) adds ~1.5× overhead on top.
    Per 1 000 chunks ≈ 30 MB total (vectors + index).
    Expected scale:
        10 000 chunks →  ~300 MB
        43 000 chunks →  ~1.3 GB
       100 000 chunks →  ~3.0 GB
    Current EC2 has ~5-6 GB free — 43K chunks fits comfortably.
"""

import argparse
import json
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import tiktoken
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Config ────────────────────────────────────────────────────────────────────

CHUNK_TOKENS       = 800         # max tokens per chunk
OVERLAP_TOKENS     = 80          # token overlap between consecutive chunks of same email
EMBEDDING_DIM      = 3072
EMBEDDING_MODEL    = "models/gemini-embedding-001"
# Gemini embedding is throttled to ~30k input tokens per MINUTE, per key. So the
# throughput lever is not request count but tokens/min: keep every embed call well
# under the ceiling, track a rolling-60s token spend per key, and route each call
# to whichever key still has headroom. 8 keys → up to ~8× the single-key rate.
PER_CALL_TOKENS    = 12000       # cap tokens per single embed call (well under 30k/min)
MAX_ITEMS_PER_CALL = 100         # Gemini batchEmbedContents item cap
PER_KEY_TPM        = 28000       # per-key rolling-60s token budget (margin under 30k)
TPM_WINDOW         = 60.0        # seconds — the TPM sliding window
DB_BATCH_SIZE      = 200         # emails fetched per DB page
KEY_COOLDOWN_SECS  = 65          # 429 backstop: sit a key out one full minute window

# 8 alive keys (4 original + 4 new)
GEMINI_KEYS: list[str] = [k for k in [
    os.environ.get("GOOGLE_API_KEY"),
    os.environ.get("GEMINI_API_KEY_2"),
    os.environ.get("GEMINI_API_KEY_6"),
    os.environ.get("GEMINI_API_KEY_10"),
    os.environ.get("GEMINI_API_KEY_13"),
    os.environ.get("GEMINI_API_KEY_14"),
    os.environ.get("GEMINI_API_KEY_15"),
    os.environ.get("GEMINI_API_KEY_16"),
] if k]

if not GEMINI_KEYS:
    sys.exit(
        "No Gemini API keys found.\n"
        "Set GOOGLE_API_KEY (and optionally GEMINI_API_KEY_2..12) in .env"
    )

# ── Tokeniser ─────────────────────────────────────────────────────────────────

_enc = tiktoken.get_encoding("cl100k_base")   # close proxy for Gemini tokenisation


def _tok(text: str) -> list[int]:
    return _enc.encode(text or "")


def _detok(tokens: list[int]) -> str:
    return _enc.decode(tokens)


# ── Chunker ───────────────────────────────────────────────────────────────────

def chunk_email(
    gmail_email_id: str,
    subject: str,
    sender_name: str,
    sender_email: str,
    sent_at: str,
    body: str,
    snippet: str,
    labels: list[str],
) -> list[dict]:
    """
    Split one email into ≤CHUNK_TOKENS chunks with OVERLAP_TOKENS overlap.
    Every chunk gets a header prepended so it is self-contained for retrieval.
    Returns a list of chunk dicts ready for embedding + DB insert.
    """
    header = (
        f"Subject: {subject or '(no subject)'}\n"
        f"From: {sender_name} <{sender_email}>\n"
        f"Date: {sent_at}\n"
        f"Labels: {', '.join(labels) if labels else 'none'}\n"
        "---\n"
    )
    body_text = (body or snippet or "").strip() or "(no body)"

    header_toks = _tok(header)
    body_toks   = _tok(body_text)

    effective = CHUNK_TOKENS - len(header_toks)

    if effective <= 0:
        # Pathological: header alone exceeds budget — chunk raw tokens
        all_toks = header_toks + body_toks
        step = max(CHUNK_TOKENS - OVERLAP_TOKENS, 1)
        raw_chunks = [
            _detok(all_toks[i : i + CHUNK_TOKENS])
            for i in range(0, len(all_toks), step)
        ]
    elif len(body_toks) <= effective:
        raw_chunks = [header + body_text]
    else:
        step = max(effective - OVERLAP_TOKENS, 1)
        raw_chunks = [
            header + _detok(body_toks[i : i + effective])
            for i in range(0, len(body_toks), step)
        ]

    total = len(raw_chunks)
    base_meta = {
        "gmail_email_id": gmail_email_id,
        "subject":        subject or "",
        "sender_name":    sender_name or "",
        "sender_email":   sender_email or "",
        "sent_at":        sent_at or "",
        "labels":         labels or [],
        "total_chunks":   total,
    }

    return [
        {
            "source_id":      f"{gmail_email_id}__chunk{idx}",
            "gmail_email_id": gmail_email_id,
            "content":        text,
            "metadata":       {**base_meta, "chunk_index": idx,
                               "source_id": f"{gmail_email_id}__chunk{idx}"},
        }
        for idx, text in enumerate(raw_chunks)
    ]


# ── Gemini key pool ───────────────────────────────────────────────────────────

@dataclass
class _KeyState:
    key: str
    spent: "deque[tuple[float, int]]" = None   # (timestamp, tokens) in the last window
    cooldown_until: float = 0.0                # set only on a 429, as a backstop

    def __post_init__(self) -> None:
        if self.spent is None:
            self.spent = deque()

    def _prune(self, now: float) -> None:
        while self.spent and now - self.spent[0][0] >= TPM_WINDOW:
            self.spent.popleft()

    def available(self, now: float) -> int:
        """Tokens this key may still send right now (0 while cooling)."""
        if now < self.cooldown_until:
            return 0
        self._prune(now)
        return max(0, PER_KEY_TPM - sum(t for _, t in self.spent))

    def charge(self, now: float, tokens: int) -> None:
        self.spent.append((now, tokens))

    def free_at(self, now: float, need: int) -> float:
        """Earliest monotonic time this key will have >= `need` budget."""
        if now < self.cooldown_until:
            return self.cooldown_until
        self._prune(now)
        used = sum(t for _, t in self.spent)
        if PER_KEY_TPM - used >= need:
            return now
        must_age = used + need - PER_KEY_TPM      # tokens that must fall out of window
        freed = 0
        for ts, tok in self.spent:
            freed += tok
            if freed >= must_age:
                return ts + TPM_WINDOW
        return now + TPM_WINDOW


class GeminiKeyPool:
    """Routes each embed call to the key with the most rolling-60s token budget.
    Sleeps only when every key is momentarily saturated. A 429 is treated as a
    backstop (cool the key one window); 401 removes the key permanently."""

    def __init__(self, keys: list[str]) -> None:
        self._states: list[_KeyState] = [_KeyState(k) for k in keys]
        self._embedders: dict[str, object] = {}
        print(f"[pool] {len(keys)} keys loaded  "
              f"(~{PER_KEY_TPM:,} tok/key/min → ~{PER_KEY_TPM*len(keys):,} tok/min aggregate).",
              flush=True)

    def _embedder(self, state: _KeyState):
        emb = self._embedders.get(state.key)
        if emb is None:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            emb = GoogleGenerativeAIEmbeddings(
                model=EMBEDDING_MODEL,
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=EMBEDDING_DIM,
                google_api_key=state.key,
            )
            self._embedders[state.key] = emb
        return emb

    def _pick(self, now: float, need: int) -> Optional[_KeyState]:
        best, best_avail = None, 0
        for s in self._states:
            av = s.available(now)
            if av >= need and av > best_avail:
                best, best_avail = s, av
        return best

    def embed(self, texts: list[str], tokens: int) -> list[list[float]]:
        """Embed `texts` (~`tokens` total) on a key with budget; block if none."""
        while True:
            if not self._states:
                sys.exit("[pool] All keys dead (401). Add fresh GEMINI_API_KEY_* and re-run.")

            now   = time.monotonic()
            state = self._pick(now, tokens)
            if state is None:
                wake = min(s.free_at(now, tokens) for s in self._states)
                wait = max(wake - now, 0.5)
                print(f"  [pool] all {len(self._states)} keys at budget — "
                      f"waiting {wait:.1f}s for headroom …", flush=True)
                time.sleep(wait)
                continue

            state.charge(now, tokens)                 # reserve budget before the call
            try:
                return self._embedder(state).embed_documents(texts)

            except Exception as exc:
                msg = str(exc)

                # Rate limit slipped through → cool this key one window, try another.
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
                    state.cooldown_until = time.monotonic() + KEY_COOLDOWN_SECS
                    print(f"  [pool] key …{state.key[-8:]} 429 → cooldown "
                          f"{KEY_COOLDOWN_SECS}s (backstop), rerouting", flush=True)
                    continue

                # Permanent auth failure → drop the key for good.
                if "401" in msg or "UNAUTHENTICATED" in msg or "ACCOUNT_STATE_INVALID" in msg:
                    print(f"  [pool] key …{state.key[-8:]} dead (401) — removing "
                          f"({len(self._states)-1} left).", flush=True)
                    self._states.remove(state)
                    self._embedders.pop(state.key, None)
                    continue

                raise  # anything else propagates


# ── DB helpers ────────────────────────────────────────────────────────────────

def _already_indexed() -> set[str]:
    from src.lib.db import pool as db
    try:
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT metadata->>'source_id' FROM email_embedding "
                    "WHERE metadata ? 'source_id'"
                )
                return {r[0] for r in cur.fetchall() if r[0]}
    except Exception as exc:
        print(f"[warn] Could not read existing index: {exc}", file=sys.stderr)
        return set()


def _count_emails() -> int:
    from src.lib.db import pool as db
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM email")
            return cur.fetchone()[0]


def _iter_emails(page_size: int = DB_BATCH_SIZE):
    """Page through every email row with sender name + labels joined in."""
    from src.lib.db import pool as db
    offset = 0
    while True:
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        e.gmail_email_id,
                        COALESCE(e.subject, '')                              AS subject,
                        COALESCE(NULLIF(u.display_name,''), u.email)         AS sender_name,
                        u.email                                              AS sender_email,
                        TO_CHAR(e.sent_at AT TIME ZONE 'UTC',
                                'YYYY-MM-DD HH24:MI UTC')                    AS sent_at,
                        COALESCE(e.body, '')                                 AS body,
                        COALESCE(e.snippet, '')                              AS snippet,
                        COALESCE(
                            ARRAY(SELECT el.label FROM email_label el
                                  WHERE el.email_id = e.id),
                            ARRAY[]::text[]
                        )                                                    AS labels
                    FROM email e
                    JOIN email_user u ON u.id = e.sender_id
                    ORDER BY e.sent_at
                    LIMIT %s OFFSET %s
                    """,
                    (page_size, offset),
                )
                rows = cur.fetchall()
        if not rows:
            break
        yield from rows
        offset += page_size


def _to_pgvector(emb: list[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in emb) + "]"


def _insert_batch(chunks: list[dict], embeddings: list[list[float]]) -> int:
    from src.lib.db import pool as db
    inserted = 0
    with db.connection() as conn:
        with conn.cursor() as cur:
            for chunk, emb in zip(chunks, embeddings):
                cur.execute("SAVEPOINT sp")
                try:
                    cur.execute(
                        f"""
                        INSERT INTO email_embedding
                            (id, gmail_email_id, content, embedding, metadata)
                        VALUES (gen_random_uuid(), %s, %s,
                                %s::vector({EMBEDDING_DIM}), %s::jsonb)
                        """,
                        (
                            chunk["gmail_email_id"],
                            chunk["content"],
                            _to_pgvector(emb),
                            json.dumps(chunk["metadata"]),
                        ),
                    )
                    cur.execute("RELEASE SAVEPOINT sp")
                    inserted += 1
                except Exception as exc:
                    cur.execute("ROLLBACK TO SAVEPOINT sp")
                    print(f"  [skip] {chunk['source_id']}: {exc}", file=sys.stderr)
        conn.commit()
    return inserted


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true",
                        help="Count chunks + estimate storage, no embedding.")
    parser.add_argument("--truncate", action="store_true",
                        help="TRUNCATE email_embedding before building (clean rebuild).")
    args = parser.parse_args()

    from src.lib.db import pool as db  # noqa — triggers DB init

    if args.truncate:
        with db.connection() as conn:
            conn.execute("TRUNCATE email_embedding")
            conn.commit()
        print("[truncate] email_embedding cleared.\n")

    total_emails = _count_emails()

    print("=" * 60)
    print(f"Emails in DB   : {total_emails:,}")
    print(f"Chunk size     : {CHUNK_TOKENS} tokens  (overlap {OVERLAP_TOKENS} tokens)")
    print(f"Embedding dim  : {EMBEDDING_DIM}-d  ({EMBEDDING_MODEL})")
    print(f"Per call       : <= {PER_CALL_TOKENS:,} tok / <= {MAX_ITEMS_PER_CALL} items")
    print(f"Key pool       : {len(GEMINI_KEYS)} keys @ ~{PER_KEY_TPM:,} tok/key/min")
    print("=" * 60)

    if args.dry_run:
        print("\n[dry-run] Counting chunks (no embedding) …")
        total_chunks = 0
        for row in _iter_emails():
            gid, subj, sname, semail, sat, body, snip, lbls = row
            total_chunks += len(chunk_email(gid, subj, sname, semail, sat, body, snip, list(lbls)))
        size_mb   = total_chunks * 12_288 / 1_048_576
        index_mb  = size_mb * 1.5
        print(f"\n[dry-run] {total_emails:,} emails → {total_chunks:,} chunks")
        print(f"[dry-run] Raw vector storage : ~{size_mb:.0f} MB")
        print(f"[dry-run] + HNSW index       : ~{index_mb:.0f} MB")
        print(f"[dry-run] Total estimate      : ~{size_mb + index_mb:.0f} MB")
        return

    seen     = _already_indexed()
    key_pool = GeminiKeyPool(GEMINI_KEYS)
    batch: list[dict] = []
    batch_tokens = 0
    total_chunks_seen = total_skipped = total_inserted = batch_num = 0
    t0 = time.monotonic()

    print(f"\nAlready indexed : {len(seen):,} chunks (will skip)\nStarting …\n")

    def flush() -> None:
        nonlocal batch, batch_tokens, batch_num, total_inserted
        if not batch:
            return
        batch_num += 1
        embs = key_pool.embed([c["content"] for c in batch], batch_tokens)
        ins  = _insert_batch(batch, embs)
        total_inserted += ins
        elapsed = time.monotonic() - t0
        rate    = total_inserted / elapsed if elapsed > 0 else 0
        print(
            f"  Batch {batch_num:5d} | +{ins:3d} | ~{batch_tokens:5d} tok | "
            f"total {total_inserted:7,} | {rate:.1f} chunks/s",
            flush=True,
        )
        batch = []
        batch_tokens = 0

    for row in _iter_emails():
        gid, subj, sname, semail, sat, body, snip, lbls = row
        for chunk in chunk_email(gid, subj, sname, semail, sat, body, snip, list(lbls)):
            total_chunks_seen += 1
            if chunk["source_id"] in seen:
                total_skipped += 1
                continue
            ctok = len(_tok(chunk["content"]))
            if batch and (batch_tokens + ctok > PER_CALL_TOKENS
                          or len(batch) >= MAX_ITEMS_PER_CALL):
                flush()
            batch.append(chunk)
            batch_tokens += ctok

    flush()   # final partial batch

    elapsed  = time.monotonic() - t0
    size_mb  = total_inserted * 12_288 / 1_048_576
    index_mb = size_mb * 1.5

    print(f"\n{'=' * 60}")
    print(f"Done in              : {elapsed/60:.1f} min")
    print(f"Emails processed     : {total_emails:,}")
    print(f"Chunks seen          : {total_chunks_seen:,}")
    print(f"Chunks skipped       : {total_skipped:,}  (already indexed)")
    print(f"Chunks inserted      : {total_inserted:,}")
    print(f"Raw vector storage   : ~{size_mb:.0f} MB")
    print(f"+ HNSW index (~1.5×) : ~{index_mb:.0f} MB")
    print(f"Total DB footprint   : ~{size_mb + index_mb:.0f} MB")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
