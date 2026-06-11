import os
from datetime import datetime

import pytz
import json
from dotenv import load_dotenv
from typing import Annotated
from rich.console import Console
from rich.markdown import Markdown
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, MessagesState, START

load_dotenv(override=True)

from lib.prompts import SYSTEM_PROMPT
from services.thread_service import ThreadService

from tools.semantic_search_tool import semantic_search_tool
from tools.metadata_filtering_tool import email_filtering_tool

# ============================================================
# CONFIG & GLOBALS
# ============================================================
console = Console()
IST = pytz.timezone("Asia/Kolkata")
today_date = datetime.now(IST).strftime("%B %d, %Y")

GEMINI_API_KEY = os.environ["GOOGLE_API_KEY"]


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


tools = [email_filtering_tool, semantic_search_tool]
tool_node = ToolNode(tools)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",
    temperature=0.4,
    max_retries=2,
    google_api_key=GEMINI_API_KEY,
)

llm = llm.bind_tools(tools)


def call_model(state: MessagesState):
    response = llm.invoke(state["messages"])
    return {"messages": [response]}


def build_agent_graph():
    """Compile the LangGraph agent once."""

    builder = StateGraph(MessagesState)

    builder.add_node("agent", call_model)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
    )
    builder.add_edge("tools", "agent")

    return builder.compile()


# png_bytes = graph.get_graph().draw_mermaid_png()

# with open("agent_graph.png", "wb") as f:
#     f.write(png_bytes)

# print("Graph saved as agent_graph.png")


# ============================================================
# CHAT LOOP
# ============================================================
def chat_loop(user_id: str) -> None:
    """Main interactive chat loop."""

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
                    "content": SYSTEM_PROMPT.format(today_date=today_date),
                },
                *last_msgs,
                {
                    "role": "user",
                    "content": user_input,
                },
            ]
        }

        result = agent_graph.invoke(state)
        airesponse = result["messages"][-1]

        response = None
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
