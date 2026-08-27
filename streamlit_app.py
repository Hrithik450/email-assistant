import pytz
import streamlit as st
from datetime import datetime
from typing import Annotated
from typing_extensions import TypedDict


st.set_page_config(page_title="AI Email Assistant", page_icon="📧")

# Import the tools and agent components from your existing files
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, START
from src.lib.prompts import SYSTEM_PROMPT
from src.lib.router import get_tier_and_model, MODEL_TIERS
from src.lib.utils import render_for_display

from src.tools.semantic_search_tool import semantic_search_tool
from src.tools.relational_query_tool import relational_query_tool


# Import your database logic
from src.services.thread_service import ThreadService

# -------------------- CONFIG --------------------
IST = pytz.timezone("Asia/Kolkata")
today_date = datetime.now(IST).strftime("%B %d, %Y")
USER_ID = "63f05e7a-35ac-4deb-9f38-e2864cdf3a1d"  # Hardcoded for this example

tools = [semantic_search_tool, relational_query_tool]
tool_node = ToolNode(tools)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    model_tier: str  # "simple" | "standard" | "complex"





@st.cache_resource
def initialize_agent():
    """
    Initializes and compiles the LangGraph agent.
    This is cached to avoid rebuilding the graph on every interaction.
    """
    print("Initializing LangGraph agent...")

    def route_model(state: AgentState) -> AgentState:
        """Classify query complexity and pick the appropriate Gemini tier."""
        latest_human_message = next(
            (
                m
                for m in reversed(state["messages"])
                if getattr(m, "type", None) == "human"
            ),
            None,
        )
        query = latest_human_message.content if latest_human_message else ""
        tier, model = get_tier_and_model(query)
        print(f"Routing → {model} ({tier})")
        return {"model_tier": tier}

    def call_model(state: AgentState) -> AgentState:
        """Send messages to the tier-appropriate model and return its response."""
        tier = state.get("model_tier", "standard")
        model_name = MODEL_TIERS.get(tier, MODEL_TIERS["standard"])
        
        from src.lib.gemini_pool import get_llm, mark_key_exhausted
        
        last_err = None
        for attempt in range(2):
            is_native = (attempt == 0) # Try native first, then fallback conceptually
            try:
                llm = get_llm(model_name, tools)
                # Check which key was used based on the base_url
                used_native = not hasattr(llm, "base_url") or "aicredits" not in str(getattr(llm, "base_url", ""))
                
                response = llm.invoke(input=state["messages"])
                return {"messages": [response]}
            except Exception as e:
                err_str = str(e)
                if any(x in err_str for x in ["429", "503", "401", "403", "insufficient_quota"]):
                    print("LLM API key exhausted, marking 60s cooldown...")
                    # Assume we exhausted the one we just tried to get
                    # But get_llm handles the fallback. We just mark the currently active one
                    used_native = True if "openai.com" in err_str else False 
                    # Actually get_llm might have returned native, and it failed.
                    mark_key_exhausted(is_native=used_native, cooldown_secs=60)
                    last_err = e
                    continue
                raise e
        raise RuntimeError(f"All LLM keys exhausted. Last error: {last_err}")

    builder = StateGraph(AgentState)

    builder.add_node("router", route_model)
    builder.add_node("agent", call_model)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "router")
    builder.add_edge("router", "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    agent_graph = builder.compile()
    return agent_graph


# --- Load cached resources ---
email_agent_graph = initialize_agent()

# -------------------- SESSION STATE INITIALIZATION --------------------
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# -------------------- NEW: ENHANCED SIDEBAR --------------------
st.sidebar.title("Chat Sessions")

if st.sidebar.button("➕ New Chat", use_container_width=True):
    # Use the first user prompt as the title for the new chat
    st.session_state.thread_id = ThreadService.create_new_thread(
        user_id=USER_ID, title="New Conversation"
    )
    st.session_state.messages = []
    st.rerun()

# --- NEW: Section for managing the CURRENTLY active chat ---
if st.session_state.thread_id:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Manage Chat")

    # Find the current thread's title to pre-fill the text input
    threads = ThreadService.get_threads(USER_ID)
    current_thread = next(
        (t for t in threads if t["id"] == st.session_state.thread_id), None
    )
    current_title = current_thread["title"] if current_thread else ""

    # RENAME functionality
    new_title = st.sidebar.text_input(
        "Rename chat", value=current_title, key=f"rename_{st.session_state.thread_id}"
    )
    if st.sidebar.button("Save Name", use_container_width=True):
        if new_title and new_title != current_title:
            ThreadService.rename_thread(st.session_state.thread_id, new_title)
            st.sidebar.success("Renamed!")
            st.rerun()

    # DELETE functionality with confirmation
    with st.sidebar.expander("Delete Chat"):
        st.warning("This action cannot be undone.")
        if st.button("Confirm Delete", use_container_width=True, type="primary"):
            ThreadService.delete_thread(st.session_state.thread_id)
            st.session_state.thread_id = None
            st.session_state.messages = []
            st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("**Previous Chats**")

# List all existing threads with their creation dates
all_threads = ThreadService.get_threads(USER_ID)
for thread in all_threads:
    # Use columns for a cleaner layout
    col1, col2 = st.sidebar.columns([3, 1])
    with col1:
        if st.button(thread["title"], key=thread["id"], use_container_width=True):
            st.session_state.thread_id = thread["id"]
            st.session_state.messages = []
            st.rerun()
    with col2:
        # Display the formatted date next to the button
        created_at = datetime.fromisoformat(thread["created_at"])
        st.caption(created_at.strftime("%b %d"))

# -------------------- STREAMLIT UI --------------------
# st.set_page_config(page_title="AI Email Assistant", page_icon="📧")
st.title("📧 AI Email Assistant")
st.write(
    "Ask me anything about your emails. I can search for content, filter by sender/date, and more."
)

# If no thread is selected, show a welcome message
if not st.session_state.thread_id:
    st.info("Select a chat from the sidebar, start a new one, or just type below.")

# Load messages for the current thread if they haven't been loaded yet
if st.session_state.thread_id and not st.session_state.messages:
    thread_history = ThreadService.get_thread_messages(st.session_state.thread_id)
    messages_from_db = thread_history.get("messages", [])

    st.session_state.messages = messages_from_db

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            st.markdown(render_for_display(message["content"]))
        else:
            st.markdown(message["content"])

# Accept user input
if input := st.chat_input("Ask a question about your emails..."):
    # Auto-create a thread if none exists
    if not st.session_state.thread_id:
        st.session_state.thread_id = ThreadService.create_new_thread(
            user_id=USER_ID, title="New Conversation"
        )

    # Add user's original message to chat history and display it
    st.session_state.messages.append({"role": "user", "content": input})
    with st.chat_message("user"):
        st.markdown(input)

    # Display assistant response
    with st.chat_message("assistant"):
        # Get the recent message history for context
        conversation_history = ThreadService.get_recent_thread_messages(
            st.session_state.thread_id
        ).get("messages", [])

        initialState = {
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(today_date=today_date),
                },
                *conversation_history,
                {
                    "role": "user",
                    "content": input,
                },
            ]
        }

        agent_answer = ""
        final_message = None
        
        with st.status("Agent is thinking...", expanded=True) as status:
            for output in email_agent_graph.stream(initialState):
                for node_name, state_update in output.items():
                    if node_name == "router":
                        tier = state_update.get("model_tier", "standard")
                        status.write(f"🧠 **Router**: Selected '{tier}' complexity tier.")
                    elif node_name == "agent":
                        msgs = state_update.get("messages", [])
                        if msgs:
                            last_msg = msgs[-1]
                            if getattr(last_msg, "tool_calls", None):
                                for tc in last_msg.tool_calls:
                                    status.write(f"🛠️ **Tool Call**: Executing `{tc['name']}`...")
                            else:
                                status.write("✅ **Agent**: Formulating final answer...")
                                final_message = last_msg
                    elif node_name == "tools":
                        status.write("📊 **Database**: Returned search results.")
                        
            status.update(label="Finished!", state="complete", expanded=False)

        if final_message:
            if isinstance(final_message.content, str):
                agent_answer = final_message.content
            elif isinstance(final_message.content, list):
                agent_answer = "\n".join(
                    block["text"]
                    for block in final_message.content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            else:
                agent_answer = str(final_message.content)
        else:
            agent_answer = "Error: Could not generate response."

        st.markdown(render_for_display(agent_answer))

    # ---- Persist both messages to the database ----
    ThreadService.update_thread_messages(
        st.session_state.thread_id,
        [
            {"role": "user", "content": input},
            {"role": "assistant", "content": agent_answer},
        ],
    )
    st.session_state.messages.append({"role": "assistant", "content": agent_answer})
