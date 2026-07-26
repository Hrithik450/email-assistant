"""
Sample evaluation test cases derived from sample.json.

These cases test the RAG pipeline's ability to retrieve and answer questions
about the one email record loaded during development.

Structure of each case:
  query            - the user's natural language question
  context          - what the search tool would return (simulated for unit tests)
  answer           - a plausible agent answer
  expected_keywords - substrings that a correct answer should contain (for fast checks)
  label            - human-readable name
"""

# ---------------------------------------------------------------------------
# Simulated "retrieved context" blocks (what semantic_search_tool returns)
# ---------------------------------------------------------------------------

_CONTEXT_EMAIL_1 = """\
[id: 18f3df9fb1898c38]
From: milin sharma <milinsharma@gmail.com>
To: Akshata Patil <akshata@2getherments.com>
CC: Customer Communications 2g CX <customer.communications@2getherments.com>, Harinath Rao <hari@2getherments.com>
Subject: Re: Greetings from Hoodi "2G-Tula" Unit no.515
Date: Fri, May 03, 2024 03:52 PM
Snippet: Thank you Akshata for your time today. It was a fruitful discussion. Looking forward to final costing, bank details etc. and the handover timelines.
Labels: IMPORTANT, CATEGORY_PERSONAL, INBOX
Attachments: image.png (image/png, 147374 bytes)
"""

_CONTEXT_EMPTY = "No relevant documents found."

_CONTEXT_IRRELEVANT = """\
[id: 00000000deadbeef]
From: noreply@spam.com
Subject: You won a prize!
Snippet: Click here to claim your reward.
Labels: SPAM
"""

# ---------------------------------------------------------------------------
# RAG test cases
# ---------------------------------------------------------------------------

RAG_TEST_CASES = [
    {
        "label": "sender_lookup",
        "query": "Who sent the email about Unit 515 at Hoodi?",
        "context": _CONTEXT_EMAIL_1,
        "answer": "The email was sent by Milin Sharma (milinsharma@gmail.com).",
        "expected_keywords": ["milin sharma", "milinsharma@gmail.com"],
    },
    {
        "label": "recipient_lookup",
        "query": "Who was the email about 2G-Tula addressed to?",
        "context": _CONTEXT_EMAIL_1,
        "answer": "The email was addressed to Akshata Patil at akshata@2getherments.com.",
        "expected_keywords": ["akshata patil", "akshata@2getherments.com"],
    },
    {
        "label": "attachment_info",
        "query": "What attachment was included in the email from Milin Sharma?",
        "context": _CONTEXT_EMAIL_1,
        "answer": "The email included an attachment named image.png (image/png, ~144 KB).",
        "expected_keywords": ["image.png", "image/png"],
    },
    {
        "label": "label_lookup",
        "query": "What labels are on the email about Hoodi Unit 515?",
        "context": _CONTEXT_EMAIL_1,
        "answer": "The email is labeled IMPORTANT, CATEGORY_PERSONAL, and INBOX.",
        "expected_keywords": ["IMPORTANT", "INBOX"],
    },
    {
        "label": "no_results_handling",
        "query": "Show me emails about the Mars mission",
        "context": _CONTEXT_EMPTY,
        "answer": "I could not find any emails about the Mars mission in our records.",
        "expected_keywords": ["not find", "mars"],
    },
    {
        "label": "irrelevant_context",
        "query": "Who sent the email from Milin Sharma?",
        "context": _CONTEXT_IRRELEVANT,
        "answer": "The search returned a spam email — no relevant result for Milin Sharma was found.",
        "expected_keywords": ["milin sharma"],
    },
    {
        "label": "faithful_grounding",
        "query": "What did Milin Sharma discuss in the email?",
        "context": _CONTEXT_EMAIL_1,
        "answer": (
            "Milin Sharma thanked Akshata Patil for their discussion and mentioned looking "
            "forward to final costing, bank details, and handover timelines."
        ),
        "expected_keywords": ["costing", "handover"],
    },
    {
        "label": "hallucination_check",
        "query": "What is the price of Unit 515?",
        "context": _CONTEXT_EMAIL_1,
        "answer": "The email does not mention a specific price for Unit 515.",
        "expected_keywords": ["not mention", "price"],
    },
]

# ---------------------------------------------------------------------------
# Agent test cases (query + expected answer for correctness check)
# ---------------------------------------------------------------------------

AGENT_TEST_CASES = [
    {
        "label": "basic_sender_query",
        "query": "Who sent the most recent email?",
        "expected_answer": "Milin Sharma",
        "tool_calls": ["email_filtering_tool"],
    },
    {
        "label": "label_filter_query",
        "query": "Show me emails marked as IMPORTANT",
        "expected_answer": "Milin Sharma",
        "tool_calls": ["email_filtering_tool"],
    },
    {
        "label": "complex_analysis",
        "query": "Summarize all the communication threads and identify any pending actions",
        "expected_answer": "handover timelines",
        "tool_calls": ["semantic_search_tool"],
    },
    {
        "label": "greeting",
        "query": "Hello, how are you?",
        "expected_answer": "Hello",
        "tool_calls": [],
    },
]
