from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Dict, Set, Optional, Tuple, List
from langchain_core.messages import HumanMessage
from datetime import datetime, timezone
from rapidfuzz import fuzz, process
import polars as pl
import json
import time
import os
import re

BASE_DIR = os.path.dirname(__file__)

CHROMA_COLLECTION_NAME = "organization_data"

EMAIL_JSON_PATH = os.path.join(BASE_DIR, "data", "raw_mails.jsonl")

EMBEDDING_MODEL_NAME = "text-embedding-3-large"

_ID_TAG_RE = re.compile(r"\s*<(id|tid)>.*?</\1>", re.IGNORECASE | re.DOTALL)
_SOURCES_SPLIT_RE = re.compile(r"(?im)^[ \t>*-]*sources\s*:?[ \t]*$|\bsources\s*:")
_SOURCE_ENTRY_RE = re.compile(r"(.*?)<id>(.*?)</id>", re.IGNORECASE | re.DOTALL)


def strip_id_tags(text: str) -> str:
    """Remove <id>...</id> / <tid>...</tid> markers for user-facing display.

    The tagged form is kept in storage and conversation history so ids stay
    available as context for follow-up queries; only the displayed copy is cleaned.
    """
    if not text:
        return text
    cleaned = _ID_TAG_RE.sub("", text)
    # Tidy separators left dangling once a trailing id is removed (e.g. "Subject (Date) —").
    cleaned = re.sub(r"[ \t]*[—\-|]\s*$", "", cleaned, flags=re.MULTILINE)
    return cleaned.rstrip()


def _clean_source_label(label: str) -> str:
    """Normalize a raw source entry into a clean one-line label."""
    label = _ID_TAG_RE.sub("", label)
    label = " ".join(label.split())  # collapse newlines / runs of whitespace
    label = label.lstrip("-*•·—| \t")  # drop leading bullet / separator noise
    return label.strip(" \t—-|")


def _render_sources_block(raw_sources: str) -> str:
    """Dedup source entries and render them as clean markdown bullets."""
    entries: list[str] = []
    seen: set[str] = set()

    matches = list(_SOURCE_ENTRY_RE.finditer(raw_sources))
    if matches:
        for m in matches:
            label = _clean_source_label(m.group(1))
            email_id = m.group(2).strip()
            key = email_id or label.lower()
            if not label or key in seen:
                continue
            seen.add(key)
            entries.append(label)
    else:
        # No id tags — fall back to line-based dedup.
        for line in raw_sources.splitlines():
            label = _clean_source_label(line)
            if not label or label.lower() in seen:
                continue
            seen.add(label.lower())
            entries.append(label)

    if not entries:
        return ""
    bullets = "\n".join(f"- {e}" for e in entries)
    return f"Sources:\n{bullets}"


def render_for_display(text: str) -> str:
    """Prepare an assistant reply for the end user.

    Strips id tags from the body and rewrites the trailing "Sources" section as a
    deduplicated markdown bullet list. Storage keeps the original tagged text.
    """
    if not text:
        return text

    parts = _SOURCES_SPLIT_RE.split(text, maxsplit=1)
    body = strip_id_tags(parts[0]).rstrip()

    if len(parts) == 1:
        return body

    sources = _render_sources_block(parts[1])
    if not sources:
        return body
    return f"{body}\n\n{sources}"


def format_date(d):
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(d, str):
        return d
    return "N/A"


def normalize_email_field(*values):
    """Normalize one or more email fields into clean lowercase emails."""
    normalized_emails = []

    for value in values:
        if isinstance(value, pl.Series):
            if value.is_empty():
                continue
            value = value.to_list()

        if not value:
            continue

        if isinstance(value, list):
            for v in value:
                cleaned = re.sub(r"[\"\'<>]", "", v)
                normalized_emails.append(cleaned.strip().lower())
        else:
            cleaned = re.sub(r"[\"\'<>]", "", value)
            normalized_emails.append(cleaned.strip().lower())

    return normalized_emails


def match_value_in_columns(value, column_value):
    """
    Check if the global `value` matches any entry in `column_value (from, to, cc)`.

    Matching rules:
      1. If `column_value` is a list → check each item.
      2. If `column_value` is a string → check directly.
      3. A match is considered valid if:
            - `value` is an exact substring, OR
            - fuzzy string similarity (partial_ratio) > 80.
      4. If no match found or input invalid → return False.
    """
    if not isinstance(value, str) or not value:
        return False

    # Case 1: column_value is a list
    if isinstance(column_value, list):
        for e in column_value:
            if value in e or fuzz.partial_ratio(value.lower(), e.lower()) > 80:
                return True
        return False

    # Case 2: column_value is a string
    if isinstance(column_value, str):
        return (
            value in column_value
            or fuzz.partial_ratio(value.lower(), column_value.lower()) > 80
        )

    return False


# Normalize the lists to string to apply filters
def normalize_list(lst) -> str:
    normalized = []

    if isinstance(lst, list):
        for i in lst:
            val = normalize_email_field(i)
            if isinstance(val, list):
                normalized.extend(map(str, val))  # flatten if list
            elif val is not None:
                normalized.append(str(val))

    elif lst is not None:
        val = normalize_email_field(lst)
        if isinstance(val, list):
            normalized.extend(map(str, val))
        elif val is not None:
            normalized.append(str(val))

    return ",".join(normalized)


# Helper to safely extract values
def safe_get(row, key, default=""):
    value = row.get(key, default) if isinstance(row, dict) else row[key]
    if value is None or str(value).lower() in {"nan", "none"}:
        return default
    return str(value)


def preprocess_subject(subject: str) -> str:
    if not isinstance(subject, str):
        return ""
    # Lowercase and replace symbols with space
    subject = re.sub(r"[:\-_,]", " ", subject)
    subject = re.sub(r"\s+", " ", subject)  # normalize spaces
    return subject.lower().strip()


def extract_numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d+\b", text))


def smart_subject_match(user_value: str, column_value: str) -> bool:
    if not column_value:
        return False

    user_clean = preprocess_subject(user_value)
    col_clean = preprocess_subject(column_value)

    user_nums = extract_numbers(user_clean)
    col_nums = extract_numbers(col_clean)

    # --- Number must match if present ---
    if user_nums and not (user_nums & col_nums):
        return False

    # --- Fuzzy match on remaining text ---
    fuzz_score = fuzz.token_set_ratio(user_clean, col_clean) / 100

    if user_nums:
        # numbers match → relax threshold
        return fuzz_score >= 0.65
    else:
        # no numbers → require stricter match
        return fuzz_score >= 0.85


def build_name_dict(df: pl.DataFrame) -> pl.DataFrame:
    """
    Vectorized, memory-efficient building of:
        token -> {"full": full_name, "emails": [list of emails]}

    Uses DataFrame.unpivot (replacement for deprecated melt), explode, and Polars string ops.
    """
    cols = [
        c
        for c in ["from_normalized", "to_normalized", "cc_normalized"]
        if c in df.columns
    ]
    if not cols:
        raise ValueError(
            "No normalized columns found. Expect one of: from_normalized, to_normalized, cc_normalized"
        )

    # 1) unpivot (stack the normalized columns into a single column "addr")
    stacked = df.unpivot(index=[], on=cols, variable_name="src", value_name="addr")

    stacked = stacked.filter(pl.col("addr") != "")

    stacked = stacked.with_columns(pl.col("addr").str.split(",").alias("addr_list"))

    stacked = stacked.explode("addr_list")

    stacked = stacked.with_columns(
        pl.col("addr_list").str.strip_chars().alias("addr")
    ).drop("addr_list")

    stacked = stacked.filter(pl.col("addr").is_first_distinct().alias("unique_addr"))

    return stacked


def normalize_text(s: str) -> str:
    """Normalize a name/email for robust matching."""
    if not s:
        return ""
    # replace separators with spaces, strip non-alphanumerics
    s = re.sub(r"[-_.]+", " ", s.lower())
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def get_best_match_from_token_map(
    sender: str, token_map: Dict[str, Set[str]], threshold: int = 75
) -> Optional[Tuple[str, float]]:
    """
    Return (best_full_name, score) if match >= threshold (0-100), else None.
    Uses rapidfuzz when present, otherwise difflib fallback.
    """
    if not sender or not token_map:
        return None
    sender_norm = normalize_text(sender)

    sender_lower = sender.lower().strip()
    if sender_lower in (k.lower() for k in token_map.keys()):
        # pick best full_name for that token by comparing normalized forms
        for k in token_map:
            if k.lower() == sender_lower:
                best_full = max(
                    token_map[k],
                    key=lambda f: fuzz.WRatio(sender_norm, normalize_text(f)),
                )
                best_score = fuzz.WRatio(sender_norm, normalize_text(best_full))
                if best_score >= threshold:
                    return best_full, best_score
                return None

    candidates = []
    meta = {}
    for token_key, full_names in token_map.items():
        tnorm = normalize_text(token_key)
        if tnorm:
            candidates.append(tnorm)
            # token candidate references no specific full name (None)
            meta[tnorm] = (token_key, None)
        for full in full_names:
            fnorm = normalize_text(full)
            if fnorm:
                candidates.append(fnorm)
                meta[fnorm] = (token_key, full)

    # remove duplicates while preserving meta mapping (last wins but that's okay)
    unique_choices = list(dict.fromkeys(candidates))
    match = process.extractOne(
        sender_norm, unique_choices, scorer=fuzz.WRatio, score_cutoff=threshold
    )
    if not match:
        return None
    match_str, score, _ = match  # match_str is normalized candidate
    token_key, full_name = meta.get(match_str, (None, None))
    # If the match candidate was just a token key (full_name is None),
    # pick the best full_name under that token_key
    if full_name is None and token_key is not None:
        best_full = max(
            token_map[token_key],
            key=lambda f: fuzz.WRatio(sender_norm, normalize_text(f)),
        )
        best_score = fuzz.WRatio(sender_norm, normalize_text(best_full))
        return (best_full, float(best_score)) if best_score >= threshold else None
    return (full_name, float(score))


def clean_date_in_jsonl():
    input_file = "lib/data/all_mails.jsonl"
    output_file = "lib/data/raw_mails.jsonl"

    def clean_date_str(date_str: str) -> str:
        """Clean ISO8601 timestamp string and convert to UTC."""
        if not date_str:
            return None

        date_str = date_str.strip()

        # Remove trailing Z if offset exists
        if ("+" in date_str or "-" in date_str) and date_str.endswith("Z"):
            date_str = date_str[:-1]

        # Remove double +00:00 after offset
        if date_str[-6:] == "+00:00" and ("+" in date_str[:-6] or "-" in date_str[:-6]):
            date_str = date_str[:-6]

        # Replace bare Z with +00:00
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"

        # Parse datetime with offset
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return date_str  # keep original if parsing fails

        # Convert to UTC and format as ISO string
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%S%z")

    # Process JSONL
    cleaned_data = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            record["date"] = clean_date_str(record.get("date"))
            cleaned_data.append(record)

    # Save cleaned JSONL
    with open(output_file, "w", encoding="utf-8") as f:
        for record in cleaned_data:
            f.write(json.dumps(record) + "\n")


def parse_json(raw_response):
    if not raw_response:
        return None
    match = re.search(r"\{.*?\}", raw_response, re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def parse_datetime_utc_flexible(date_str: str) -> datetime:
    """Parse various date/time formats into a UTC-aware datetime."""
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except ValueError:
        pass
    raise ValueError(f"Cannot parse date: {date_str}")


def expand_start(dt: datetime, original_str: str) -> datetime:
    """Expand start bound depending on precision."""
    if len(original_str) == 10:  # YYYY-MM-DD
        return dt.replace(hour=0, minute=0, second=0)
    else:  # exact second
        return dt


def expand_end(dt: datetime, original_str: str, start_date: str) -> datetime:
    """Expand end bound depending on precision."""
    if len(original_str) == 10:  # YYYY-MM-DD
        return dt.replace(hour=23, minute=59, second=59)
    elif len(original_str) == 16:  # YYYY-MM-DD HH:MM
        return dt.replace(second=59)
    elif len(original_str) == 19:  # YYYY-MM-DDTHH:MM:SS
        if original_str == start_date:
            if original_str.endswith("00:00"):
                return dt.replace(minute=59, second=59)
            else:
                return dt.replace(second=59)
        return dt
    return dt


def build_date_range(start_date: str, end_date: str):
    """Return (range_start, range_end) that always forms a valid interval."""
    if not start_date and not end_date:
        return None, None

    range_start = parse_datetime_utc_flexible(start_date) if start_date else None
    range_end = parse_datetime_utc_flexible(end_date) if end_date else None

    if range_start:
        range_start = expand_start(range_start, start_date)
    if range_end:
        range_end = expand_end(range_end, end_date, start_date)

    return range_start, range_end


def count_tokens(encoding_model, text: str) -> int:
    return len(encoding_model.encode(text))


def run_batch_task(
    llm: ChatGoogleGenerativeAI,
    tasks: List[Tuple[int, List[HumanMessage], int]],
    tpm_limit: int = 200000,
) -> List[Tuple[int, str]]:
    """
    tasks: list of (task_id, messages, est_tokens)
    tpm_limit: max tokens/minute allowed
    returns: list of (task_id, response_text)
    """
    results: List[Tuple[int, str]] = []
    current_batch: List[Tuple[int, List[HumanMessage], int]] = []
    current_tokens = 0
    window_start = time.time()

    def flush(batch):
        """Send a batch to the LLM and record results."""
        nonlocal results
        if not batch:
            return
        responses = llm.batch([msgs for _, msgs, _ in batch])
        for (task_id, _, _), resp in zip(batch, responses):
            results.append((task_id, resp.content))

    for task in tasks:
        _, _, tok = task

        if current_tokens + tok > tpm_limit and current_batch:
            flush(current_batch)
            current_batch, current_tokens = [], 0

            # respect TPM limit
            elapsed = time.time() - window_start
            if elapsed < 60:
                time.sleep(60 - elapsed)
            window_start = time.time()

        current_batch.append(task)
        current_tokens += tok

    if current_batch:
        flush(current_batch)

    return results
