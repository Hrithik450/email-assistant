import polars as pl
from lib.pipeline import df
from datetime import datetime
from langchain.tools import tool
from lib.utils import (
    match_value_in_columns,
    smart_subject_match,
    build_date_range,
    normalize_list,
)


def human_readable_date(timestamp) -> str:
    """
    Convert a timestamp to human-readable form.
    Accepts: str, datetime.datetime, or None
    """
    if timestamp is None:
        return "N/A"

    # If Polars datetime, convert to Python datetime
    if not isinstance(timestamp, datetime):
        try:
            # Try parsing string
            timestamp = datetime.fromisoformat(str(timestamp))
        except Exception:
            return "N/A"

    return timestamp.strftime("%a, %b %d, %Y %I:%M %p")


@tool("email_filtering_tool", parse_docstring=True)
def email_filtering_tool(
    uid: str = None,
    threadId: str = None,
    sender: str = None,
    recipient: str = None,
    subject: str = None,
    cc: bool = False,
    labels: list[str] = None,
    start_date: str = None,
    end_date: str = None,
    body: bool = False,
    html: bool = False,
    sort_by: str = "date",
    sort_order: str = "desc",
    limit: int = None,
) -> str:
    """
    This tool filter emails based on metadata such as sender (human), recipient (human), date range, or thread ID.

    Args:
        uid (str, optional): Filter emails by their unique UID. Exact match required.
        threadId: Filter emails by their conversation (email chian) thread ID, Returns all messages belonging to that specific chain (thread).
        sender (str or list of str, optional): Filter emails by sender(s). Can be full email address, partial email, or sender names (case-insensitive, only humans).
        recipient (str or list of str, optional): Filter emails by recipient(s). Can be full email addresses, partial emails, or recipient names, but strictly not numbers. (case-insensitive, only humans).
        subject (str, optional): Filter email by subject text. Can be full or partial subject string (case-insensitive).
        cc (bool, optional): Filter cc recepients of the email only when explicitly requested. Default False.
        labels (list of str, optional): Filter emails by one or more labels. Matches any email that contains at least one of the provided labels (case-insensitive).
        start_date (str, optional): Filter emails sent on or after this date. Format: 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'.
        end_date (str, optional): Filter emails sent on or before this date. Format: 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'.
        body (bool, optional): Include the plain-text email body only when explicitly requested. Default False.
        html (bool, optional): Include the full HTML body only when explicitly requested. Default False.
        sort_by (str, optional): Column to sort the results by. Default is 'date_dt'.
        sort_order (str, optional): Sort order: 'asc' for ascending, 'desc' for descending. Default is 'desc'.
        limit (int, optional): Maximum number of results to return. set default value to 5.
    """

    print(
        f"email_filtering_tool is being called {uid}, {threadId}, {sender}, {recipient}, {subject}, {cc}, {labels}, {start_date}, {end_date}, {body}, {html}, {sort_by}, {sort_order}, {limit}"
    )
    temp_df = df.clone()
    mask = pl.lit(True)

    temp_df = temp_df.with_columns(
        [
            temp_df["body"].struct.field("text").alias("body_text"),
            temp_df["body"].struct.field("html").alias("body_html"),
        ]
    )

    if uid:
        mask = mask & (pl.col("id") == uid)

    if threadId:
        mask = mask & (pl.col("threadId") == threadId)

    # --- Sender filter (case-insensitive, matches name or email) ---
    if sender:
        sender = sender.lower()
        # Add a normalized column
        temp_df = temp_df.with_columns(
            [
                pl.col("from")
                .map_elements(normalize_list, return_dtype=str)
                .alias("from_normalized")
            ]
        )
        # Filter rows where the normalized 'from' matches sender
        sender_mask = pl.col("from_normalized").map_elements(
            lambda x: match_value_in_columns(sender, x), return_dtype=bool
        )
        mask = mask & sender_mask

    # --- Recipient filter ---
    if recipient:
        recipient = recipient.lower()
        # Normalize 'to' and 'cc' columns which are lists
        temp_df = temp_df.with_columns(
            [
                pl.col("to")
                .map_elements(normalize_list, return_dtype=str)
                .alias("to_normalized")
            ]
        )
        # Filter rows where any normalized 'to' or 'cc' matches the recipient
        recipient_mask = pl.col("to_normalized").map_elements(
            lambda x: match_value_in_columns(recipient, x), return_dtype=bool
        )
        if cc:
            # Normalize 'to' and 'cc' columns which are lists
            temp_df = temp_df.with_columns(
                [
                    pl.col("cc")
                    .map_elements(normalize_list, return_dtype=str)
                    .alias("cc_normalized")
                ]
            )
            # Filter rows where any normalized 'to' or 'cc' matches the recipient
            cc_mask = pl.col("cc_normalized").map_elements(
                lambda x: match_value_in_columns(recipient, x), return_dtype=bool
            )
            recipient_mask = recipient_mask | cc_mask

        mask = mask & recipient_mask

    # --- Date filtering (normalize to datetime) ---
    dt1 = (
        pl.col("date")
        .str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False)
        .dt.replace_time_zone("UTC")
    )
    dt2 = (
        pl.col("date")
        .str.to_datetime("%Y-%m-%dT%H:%M:%S%z", strict=False)
        .dt.convert_time_zone("UTC")
    )
    temp_df = temp_df.with_columns(pl.coalesce([dt1, dt2]).alias("date_dt"))

    range_start, range_end = build_date_range(start_date, end_date)

    if range_start and range_end:
        mask = (
            mask & (pl.col("date_dt") >= range_start) & (pl.col("date_dt") <= range_end)
        )

    if labels:
        labels = [lbl.strip().lower() for lbl in labels]

        temp_df = temp_df.with_columns(
            [
                pl.col("labels")
                .map_elements(normalize_list, return_dtype=str)
                .alias("labels_normalized")
            ]
        )

        labels_mask = pl.col("labels_normalized").map_elements(
            lambda email_lables: any(lbl in email_lables for lbl in labels),
            return_dtype=bool,
        )

        mask = mask & labels_mask

    if subject:
        subject_mask = pl.col("subject").map_elements(
            lambda x: smart_subject_match(subject, x), return_dtype=bool
        )
        mask = mask & subject_mask

    # Apply the mask only once
    temp_df = temp_df.filter(mask)

    # --- Sorting ---
    temp_df = temp_df.sort(by=sort_by, descending=(sort_order.lower() == "desc"))

    # --- Handle empty result ---
    if temp_df.is_empty():
        return "No emails found matching the specified criteria."

    # --- Preview results ---
    total_matches = temp_df.height

    preview_cols = [
        "id",
        "threadId",
        "from",
        "to",
        "subject",
        "date_dt",
        "cc",
        "snippet",
        "labels",
        "attachments",
    ]
    if body:
        preview_cols.append("body_text")
    if html:
        preview_cols.append("body_html")

    if limit is None:
        results_preview = temp_df.select(preview_cols).to_dicts()
    else:
        results_preview = temp_df.head(limit).select(preview_cols).to_dicts()

    def fmt(res):
        parts = [
            f"id: {res.get('id','N/A')}",
            f"ThreadId: {res.get('threadId','N/A')}",
            f"From: {res.get('from','N/A')}",
            f"To: {res.get('to','N/A')}",
            f"CC: {res.get('cc','N/A')}",
            f"Subject: {res.get('subject','N/A')}",
            f"Date: {human_readable_date(res.get('date_dt'))}",
            f"Snippet: {res.get('snippet','N/A')}",
            f"Labels: {res.get('labels','N/A')}",
            f"Attachments: {res.get('attachments','N/A')}",
        ]
        if body:
            parts.append(f"Body: {res.get('body_text','N/A')}")
        if html:
            parts.append(f"HTML: {res.get('body_html','N/A')}")
        return "\n".join(parts)

    formatted_results = "\n\n---\n\n".join(fmt(r) for r in results_preview)

    shown = total_matches if limit is None else min(int(limit), total_matches)

    return f"Found {total_matches} emails matching the criteria. Showing {shown}:\n\n{formatted_results}"
