# --- THIS IS THE FIX ---
# It checks if the app is running on Streamlit Cloud by looking for a specific environment variable.
# The sqlite3 patch will ONLY run when deployed to the cloud.
import sys

# --- THIS IS THE NEW, ROBUST FIX ---
# This ensures the patch runs before chromadb is ever touched.
IS_STREAMLIT_ENVIRONMENT = "streamlit" in sys.modules
if IS_STREAMLIT_ENVIRONMENT:
    print("Streamlit environment detected. Applying sqlite3 patch in load_data.py.")
    try:
        __import__("pysqlite3")
        sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
        print("Successfully patched sqlite3.")
    except ImportError:
        print("pysqlite3-binary not found, skipping patch.")

import pytz
import streamlit as st
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI

st.set_page_config(page_title="AI Email Assistant", page_icon="📧")

# Import the tools and agent components from your existing files
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, MessagesState, START
from lib.prompts import SYSTEM_PROMPT

from tools.semantic_search_tool import semantic_search_tool
from tools.metadata_filtering_tool import email_filtering_tool

# This will trigger the data loading and Chroma connection via st.cache_resource
from lib.pipeline import df, chroma_collection

# Import your database logic
from services.thread_service import ThreadService

# -------------------- CONFIG --------------------
IST = pytz.timezone("Asia/Kolkata")
today_date = datetime.now(IST).strftime("%B %d, %Y")
USER_ID = "63f05e7a-35ac-4deb-9f38-e2864cdf3a1d"  # Hardcoded for this example

tools = [semantic_search_tool, email_filtering_tool]
tool_node = ToolNode(tools)


@st.cache_resource
def get_llm():
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        temperature=0.4,
        max_retries=2,
        google_api_key=st.secrets["GOOGLE_API_KEY"],
    )
    return llm.bind_tools(tools)


@st.cache_resource
def initialize_agent():
    """
    Initializes and compiles the LangGraph agent.
    This is cached to avoid rebuilding the graph on every interaction.
    """
    print("Initializing LangGraph agent...")

    def call_model(state: MessagesState) -> MessagesState:
        """
        Sends messages to the model and returns the response wrapped in MessagesState format.
        """
        response = get_llm().invoke(input=state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)

    builder.add_node("agent", call_model)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
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
        st.caption(thread["created_at"].strftime("%b %d"))

# -------------------- STREAMLIT UI --------------------
# st.set_page_config(page_title="AI Email Assistant", page_icon="📧")
st.title("📧 AI Email Assistant")
st.write(
    "Ask me anything about your emails. I can search for content, filter by sender/date, and more."
)

# If no thread is selected, show a welcome message
if not st.session_state.thread_id:
    st.info("Select a chat from the sidebar or start a new one.")
    st.stop()

# Load messages for the current thread if they haven't been loaded yet
if not st.session_state.messages:
    thread_history = ThreadService.get_thread_messages(st.session_state.thread_id)
    messages_from_db = thread_history.get("messages", [])

    st.session_state.messages = messages_from_db

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if input := st.chat_input("Ask a question about your emails..."):
    # Add user's original message to chat history and display it
    st.session_state.messages.append({"role": "user", "content": input})
    with st.chat_message("user"):
        st.markdown(input)

    # Display assistant response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            # Get the recent message history for context
            conversation_history = ThreadService.get_recent_thread_messages(
                st.session_state.thread_id
            ).get("messages", [])

            # Construct the input for the agent, matching chatbot.py's structure
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

            # Invoke the agent to get the final response
            final_state = email_agent_graph.invoke(initialState)
            airesponse = final_state["messages"][-1]

            if isinstance(airesponse.content, str):
                agent_answer = airesponse.content

            elif isinstance(airesponse.content, list):
                agent_answer = "\n".join(
                    block["text"]
                    for block in airesponse.content
                    if isinstance(block, dict) and block.get("type") == "text"
                )

            else:
                agent_answer = str(airesponse.content)

            st.markdown(agent_answer)

    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": agent_answer})

    # Save the user's original prompt and the agent's answer to the database
    ThreadService.update_thread_messages(
        st.session_state.thread_id, {"role": "user", "content": input}
    )
    ThreadService.update_thread_messages(
        st.session_state.thread_id, {"role": "assistant", "content": agent_answer}
    )
