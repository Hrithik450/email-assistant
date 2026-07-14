import os
from datetime import datetime

import pytz
from typing import Annotated
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START

from src.lib.prompts import SYSTEM_PROMPT
from src.lib.router import get_model_for_query, MODEL_TIERS
from src.services.thread_service import ThreadService

from src.tools.semantic_search_tool import semantic_search_tool
from tools.relational_query_tool import relational_query_tool
from src.tools.eval_tool import rag_eval_tool

load_dotenv(override=True)

console = Console()
IST = pytz.timezone("Asia/Kolkata")


def _make_llm(model_name: str) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.4,
        max_retries=2,
        google_api_key=os.environ["GOOGLE_API_KEY"],
    ).bind_tools(tools)


def _today_date() -> str:
    return datetime.now(IST).strftime("%B %d, %Y")


tools = [semantic_search_tool, relational_query_tool]
tool_node = ToolNode(tools)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    model_tier: str  # "simple" | "standard" | "complex"


def route_model(state: AgentState) -> AgentState:
    """
    Model routing — classify query complexity and return the appropriate Gemini model tier.

    Tiers (cheapest → best reasoning):
      simple   → gemini-2.5-flash-lite   (greetings, single-fact lookups, trivial Q&A)
      standard → gemini-2.5-flash        (email search, metadata filter, summarise 1 thread)
      complex  → gemini-3.5-flash        (multi-step analysis, cross-thread synthesis, aggregation)

    Classification is purely heuristic (no extra LLM call), so it adds zero latency / tokens.
    The router errs toward upgrading: when uncertain it picks the next tier up.
    """

    latest_human_message = next(
        (m for m in reversed(state["messages"]) if getattr(m, "type", None) == "human"),
        None,
    )

    query = latest_human_message.content if latest_human_message else ""

    model = get_model_for_query(query)
    tier = next(k for k, v in MODEL_TIERS.items() if v == model)

    console.log(f"[dim]Routing → {model} ({tier})[/dim]")
    return {"model_tier": tier}


def call_model(state: AgentState):
    tier = state.get("model_tier", "standard")
    model_name = MODEL_TIERS.get(tier, MODEL_TIERS["standard"])
    llm = _make_llm(model_name)
    response = llm.invoke(state["messages"])
    return {"messages": [response]}


def build_agent_graph():
    builder = StateGraph(AgentState)

    builder.add_node("router", route_model)
    builder.add_node("agent", call_model)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "router")
    builder.add_edge("router", "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile()


def chat_loop(user_id: str) -> None:
    thread_id = ThreadService.get_last_thread(user_id)
    if not thread_id:
        thread_id = ThreadService.create_new_thread(
            user_id=user_id, title="Email's related questions"
        )

    console.log(f"[cyan]Using thread {thread_id}[/cyan]")

    agent_graph = build_agent_graph()

    while True:
        user_input = input("\nAsk a question about your emails (type 'exit' to quit): ")
        if user_input.strip().lower() == "exit":
            break

        last_msgs = ThreadService.get_recent_thread_messages(thread_id).get(
            "messages", []
        )

        state = {
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(today_date=_today_date()),
                },
                *last_msgs,
                {
                    "role": "user",
                    "content": user_input,
                },
            ],
            "model_tier": "standard",
        }

        result = agent_graph.invoke(state)
        airesponse = result["messages"][-1]

        if isinstance(airesponse.content, str):
            response = airesponse.content
        elif isinstance(airesponse.content, list):
            response = "\n".join(
                block["text"]
                for block in airesponse.content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            response = str(airesponse.content)

        ThreadService.update_thread_messages(
            thread_id, {"role": "user", "content": user_input}
        )
        ThreadService.update_thread_messages(
            thread_id, {"role": "assistant", "content": response}
        )

        print("\n--- Final Answer ---")
        console.print(Markdown(response))
        print("--------------------\n")


if __name__ == "__main__":
    USER_ID = "63f05e7a-35ac-4deb-9f38-e2864cdf3a1d"
    chat_loop(USER_ID)
