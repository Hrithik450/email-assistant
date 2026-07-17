import re
import json
from pathlib import Path

try:
    from src.lib.helper import getaddresses, parseaddr
except ImportError:
    from helper import getaddresses, parseaddr
from datetime import datetime, timezone, timedelta

# File configuration

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[1]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "src" / "lib" / "data" / "raw_data.jsonl"
DEFAULT_OUTPUT_PATH = BASE_DIR / "data" / "norm_data.jsonl"
DEFAULT_BATCH_SIZE = 500


# Low-level helpers
def normalize_text(value):
    if value is None:
        return ""

    # Removing "" '' <>
    return re.sub(r"[\"'<>]", "", str(value)).strip()


def normalize_email_date(date: str):
    ist = timezone(timedelta(hours=5, minutes=30))

    if not date:
        return ""

    date = str(date).strip()

    try:
        dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ist).isoformat()
        return dt.astimezone(ist).isoformat()
    except ValueError:
        pass

    try:
        dt = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S %z")
        return dt.astimezone(ist).isoformat()
    except ValueError:
        pass

    try:
        dt = datetime.strptime(date, "%d %b %Y %H:%M:%S %z")
        return dt.astimezone(ist).isoformat()
    except ValueError:
        pass

    return date


def extract_display_name_from_email(email):
    if "@" not in email:
        return ""

    return email.rsplit("@", 1)[0]


def normalize_email_address(value):
    original_value = normalize_text(value)
    name, email = parseaddr(str(value or ""))
    name = normalize_text(name)
    email = normalize_text(email)

    if not email:
        email = original_value

    if "@" in email:
        email = email.lower()

    domain = email.rsplit("@", 1)[1] if "@" in email else ""
    if not name:
        name = extract_display_name_from_email(email)
    elif "@" in name:
        name = extract_display_name_from_email(name)

    return {
        "name": name,
        "email": email,
        "domain": domain,
    }


def normalize_email_address_list(value):
    if not value:
        return []

    if isinstance(value, list):
        raw_addresses = [str(item) for item in value if item]
    else:
        raw_addresses = [str(value)]

    normalized_addresses = []
    for raw_value in raw_addresses:
        addresses = getaddresses([raw_value])
        if not addresses:
            addresses = [("", raw_value)]

        for name, email in addresses:
            raw_address = f"{name} <{email}>" if name else email
            normalized_addresses.append(normalize_email_address(raw_address))

    return normalized_addresses


# Email normalization


def normalize_email_record(email):

    body = email.get("body") or {}
    if isinstance(body, dict):
        body_text = body.get("text") or ""
    else:
        body_text = str(body)

    normalized_email = {
        "id": email.get("id", ""),
        "threadId": email.get("threadId", ""),
        "date": normalize_email_date(email.get("date", "")),
        "from": normalize_email_address(email.get("from", "")),
        "to": normalize_email_address_list(email.get("to")),
        "cc": normalize_email_address_list(email.get("cc")),
        "subject": email.get("subject", ""),
        "snippet": email.get("snippet", ""),
        "body": body_text,
        "attachments": email.get("attachments") or [],
        "labels": email.get("labels") or [],
    }

    return normalized_email


def normalize_email_batch(emails):
    normalized_emails = []

    for email in emails:
        try:
            normalized_email = normalize_email_record(email)
        except Exception:
            normalized_email = {
                "id": email.get("id", "") if isinstance(email, dict) else "",
                "threadId": (
                    email.get("threadId", "") if isinstance(email, dict) else ""
                ),
                "date": email.get("date", "") if isinstance(email, dict) else "",
                "from": email.get("from", "") if isinstance(email, dict) else "",
                "to": email.get("to", []) if isinstance(email, dict) else [],
                "cc": email.get("cc", []) if isinstance(email, dict) else [],
                "subject": email.get("subject", "") if isinstance(email, dict) else "",
                "snippet": email.get("snippet", "") if isinstance(email, dict) else "",
                "body": email.get("body", "") if isinstance(email, dict) else "",
                "attachments": (
                    email.get("attachments", []) if isinstance(email, dict) else []
                ),
                "labels": email.get("labels", []) if isinstance(email, dict) else [],
            }

        normalized_emails.append(normalized_email)

    return normalized_emails


# File processing


def write_normalized_batch(batch, output_file):
    for email in normalize_email_batch(batch):
        output_file.write(json.dumps(email, ensure_ascii=False))
        output_file.write("\n")


def normalizer(input_path, output_path, batch_size=DEFAULT_BATCH_SIZE):
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    batch = []

    with (
        input_path.open("r", encoding="utf-8") as input_file,
        output_path.open("w", encoding="utf-8") as output_file,
    ):
        for line_number, line in enumerate(input_file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                batch.append(json.loads(line))
            except json.JSONDecodeError as exc:
                batch.append(
                    {
                        "raw": line,
                        "normalization_error": f"Invalid JSON on line {line_number}: {exc}",
                    }
                )

            if len(batch) >= batch_size:
                write_normalized_batch(batch, output_file)
                total += len(batch)
                batch.clear()

        if batch:
            write_normalized_batch(batch, output_file)
            total += len(batch)

    return total


if __name__ == "__main__":

    count = normalizer(
        input_path=DEFAULT_INPUT_PATH,
        output_path=DEFAULT_OUTPUT_PATH,
        batch_size=DEFAULT_BATCH_SIZE,
    )

    print(f"Normalized {count} emails into {DEFAULT_OUTPUT_PATH}")
