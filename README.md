# Email Assistant

An AI-powered enterprise knowledge assistant that enables teams to search, analyze, and answer complex business questions across emails, documents, conversations, and organizational knowledge.

## Overview

Email Assistant combines Retrieval-Augmented Generation (RAG), metadata based, and agent-based reasoning to help users quickly find information, generate insights, and answer questions from large collections of unstructured business data.

The system supports both qualitative and quantitative analysis by intelligently retrieving relevant context and leveraging specialized tools to generate accurate, explainable responses.

## Key Features

### Intelligent Knowledge Retrieval

- Semantic search across emails, documents, and structured data
- Advanced Retrieval-Augmented Generation (RAG) pipeline
- Re-ranking for improved retrieval accuracy
- Context-aware answer generation

### Agent-Based Reasoning

- Multi-step reasoning using LangGraph and LangChain
- Tool-calling capabilities for specialized analysis
- Support for both factual lookup and analytical queries
- Source-grounded responses

### Data Processing Pipeline

- Ingestion of documents, emails, and structured datasets
- Automatic chunking and embedding generation
- Metadata-aware indexing
- Efficient vector search using ChromaDB

### Interactive User Experience

- Streamlit-based chat interface
- Conversational querying
- Source attribution and contextual answers
- Fast response generation

## Supported Data Sources

- Email datasets
- JSONL records

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/tekthink-ai/email-assistant.git
cd email-assistant
```

### 2. Create a Virtual Environment

#### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

#### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root and add the required credentials:

```env
GOOGLE_API_KEY="your_google_api_key"
DATABASE_URL="postgresql://username:password@host:port/database"
REDIS_URL="redis://username:password@host:port"
CHROMA_API_KEY="your_chroma_api_key"
CHROMA_TENANT="your_chroma_tenant_id"
CHROMA_DATABASE="your_chroma_database_name"
EMAIL_JSONL_GDRIVE_ID="your_google_drive_file_id"
```

### 5. Run the Application

```bash
python main.py
```

The application will start and you can begin interacting with the assistant.

## Running the Application

### Web Interface (Recommended)

```bash
streamlit run streamlit_app.py
```

Open:

```text
http://localhost:8501
```

## Technology Stack

### AI & Agent Frameworks

- LangGraph
- LangChain
- Google Gemini

### Embeddings & NLP

- Sentence Transformers
- Hugging Face Transformers

### Retrieval Infrastructure

- ChromaDB
- Vector Search

### Data Processing

- Pandas
- Python

### User Interface

- Streamlit

## Use Cases

- Enterprise search
- Email intelligence
- Document question answering
- Internal knowledge management

## License

This project is intended for research, experimentation, and enterprise knowledge assistant development.
