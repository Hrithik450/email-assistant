import time
import tiktoken
from typing import List, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage

template = """
You are an expert email summarizer.  

Task:  
- Input: Multiple emails with metadata (id, threadId, from, to, cc, Subject, date, snippet, body, labels, attachments).  
- Group by ThreadId and summarize chronologically.  
- Capture key points, actions, and important details with clarity and brevity.

Summarize this,
{chunk}
"""
prompt_perspective = ChatPromptTemplate.from_template(template)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_completion_tokens=512)

encoding_model = tiktoken.get_encoding("cl100k_base")


def get_chunks(text: str, chunk_size: int = 10000) -> List[str]:
    """Split a large text into token-based chunks."""
    tokens = encoding_model.encode(text)

    chunks = []
    for i in range(0, len(tokens), chunk_size):
        chunk_tokens = tokens[i : i + chunk_size]
        chunk_text = encoding_model.decode(chunk_tokens)
        chunks.append(chunk_text)
    return chunks


def count_tokens(text: str) -> int:
    return len(encoding_model.encode(text))


def run_batch_task(
    tasks: List[Tuple[int, List[HumanMessage], int]], tpm_limit: int = 29000
) -> List[Tuple[int, str]]:
    """
    tasks: list of (task_id, messages, est_tokens)
    tpm_limit: max tokens/minute allowed
    returns: list of (task_id, response_text)
    """
    results: List[Tuple[int, str]] = []

    current_tokens = 0
    current_batch: List[Tuple[int, List[HumanMessage], int]] = []

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
