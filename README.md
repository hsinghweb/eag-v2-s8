# Cortex-R: Intelligent Agentic AI System

A reasoning-driven AI agent capable of using external tools, memory, and multi-modal capabilities to solve complex tasks step-by-step. The agent can receive queries via Telegram, search for information, organize data in Google Sheets, and respond with formatted results.

## 🎯 Features

- **Multi-Modal Tool Integration**: Supports both stdio and SSE (Server-Sent Events) transport layers for MCP servers
- **Telegram Integration**: Receive and process queries via Telegram bot
- **Google Sheets Integration**: Automatically create and populate Google Sheets with search results
- **Web Search**: Search the internet for real-time information
- **Document Processing**: RAG (Retrieval Augmented Generation) with PDF and document parsing
- **Memory System**: FAISS-based vector memory for context-aware responses
- **Intelligent Workflow**: 5-phase cognitive loop (Perception → Memory → Decision → Execution → Completion)
- **Error Handling**: Robust retry logic with exponential backoff for API rate limits

## 🏗️ Architecture

### Core Components

```
core/
├── loop.py          # Main agent cognitive loop (5-phase workflow)
├── session.py       # MultiMCP session manager (stdio + SSE support)
├── context.py       # Agent context and state management
└── strategy.py      # Decision-making and planning logic

modules/
├── perception.py    # LLM-based intent extraction and perception
├── memory.py        # FAISS vector memory system
├── decision.py      # Plan generation and workflow guidance
├── action.py        # Tool execution and result parsing
├── model_manager.py # LLM model management (Gemini, Ollama)
└── tools.py         # Tool summarization and filtering

MCP Servers (stdio):
├── mcp_server_1.py         # Math operations
├── mcp_server_2.py         # Document processing & RAG
├── mcp_server_3.py         # Web search
├── mcp_server_telegram.py  # Telegram message handling
└── mcp_server_gmail.py     # Email sending (SMTP)

MCP Servers (SSE):
└── mcp_server_gdrive.py    # Google Sheets/Drive operations
```

### Agent Workflow

1. **Perception**: Extract user intent, entities, scope limits from query
2. **Memory**: Retrieve relevant context from FAISS vector store
3. **Decision**: Generate execution plan using LLM
4. **Execution**: Execute tools via MCP protocol
5. **Completion**: Return final answer with Google Sheet link

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Ollama (for local embeddings)
- Google Cloud Project (for Sheets/Drive API)
- Telegram Bot Token
- Gmail App Password (for email sending)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd eag-v2-s8
   ```

2. **Install dependencies**
   ```bash
   uv pip install -e .
   ```

3. **Install Ollama models**
   ```bash
   ollama pull nomic-embed-text
   ollama pull phi3:mini  # For semantic chunking
   ```

4. **Set up environment variables**
   Create a `.env` file with:
   ```env
   # Telegram
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   
   # Gmail (SMTP)
   GMAIL_ADDRESS=your_email@gmail.com
   GMAIL_APP_PASSWORD=your_app_password
   RECIPIENT_EMAIL=recipient@gmail.com
   
   # Google APIs
   GOOGLE_DRIVE_CREDENTIALS_JSON=path/to/credentials.json
   GOOGLE_SHEETS_CREDENTIALS_JSON=path/to/credentials.json
   
   # Gemini API
   GEMINI_API_KEY=your_gemini_api_key
   ```

5. **Set up Google OAuth**
   ```bash
   python setup_google_oauth.py
   ```
   This will generate `token.json` for Google Sheets/Drive access.

6. **Start the Google Drive SSE server**
   ```bash
   python mcp_server_gdrive.py
   ```
   This starts the FastAPI server on `http://localhost:8002`

7. **Run the Telegram agent**
   ```bash
   python telegram_agent.py
   ```

## 📋 Usage

### Via Telegram

1. Start the agent: `python telegram_agent.py`
2. Send a message to your Telegram bot
3. The agent will:
   - Search for information
   - Create a Google Sheet with the data
   - Return the sheet link in Telegram

### Example Queries

- "Find the current point standings of F1 racers"
- "Get top 10 trending stocks"
- "Search for latest AI research papers"
- "Find current weather in New York"

### Via Command Line

```bash
python agent.py "Your query here"
```

## 🔧 Configuration

### Agent Profile (`config/profiles.yaml`)

```yaml
strategy:
  type: conservative
  max_steps: 50

memory:
  top_k: 3
  type_filter: tool_output
  embedding_model: nomic-embed-text

llm:
  text_generation: gemini
  embedding: nomic
```

### Models (`config/models.json`)

- **Text Generation**: Gemini 2.0 Flash (via API)
- **Embeddings**: Nomic Embed Text (via Ollama)
- **Semantic Chunking**: Phi3 Mini (via Ollama)

## 🛠️ MCP Servers

### Stdio Servers (Local)

- **Math Server**: Mathematical operations
- **Documents Server**: PDF/document parsing, RAG, semantic chunking
- **Web Search Server**: Internet search capabilities
- **Telegram Server**: Message receiving/sending
- **Gmail Server**: Email sending via SMTP

### SSE Server (HTTP)

- **Google Drive Server**: Google Sheets/Drive operations (FastAPI on port 8002)

## 📊 Features

### RAG (Retrieval Augmented Generation)
- Semantic chunking using LLM-based topic detection
- FAISS vector store for efficient similarity search
- Support for PDF, Markdown, HTML documents

### Tool Discovery
- Dynamic tool summarization
- Hint-based filtering
- Schema validation via Pydantic

### Error Handling
- Retry logic with exponential backoff for API rate limits
- Loop detection and prevention
- Graceful fallbacks

### Memory Management
- Vector embeddings for semantic search
- Tool output tracking
- Context-aware retrieval

## 🔐 Security

- Environment variables for sensitive credentials
- OAuth2 for Google APIs
- App passwords for SMTP
- Input validation via Pydantic schemas

## 📝 Project Structure

```
eag-v2-s8/
├── agent.py                    # CLI entry point
├── telegram_agent.py           # Telegram bot entry point
├── config/
│   ├── models.json             # LLM model configurations
│   └── profiles.yaml           # Agent profiles
├── core/                       # Core agent logic
│   ├── loop.py                 # Main cognitive loop
│   ├── session.py              # MCP session management
│   ├── context.py              # Context management
│   └── strategy.py             # Strategy and planning
├── modules/                     # Cognitive modules
│   ├── perception.py            # Intent extraction
│   ├── memory.py               # Memory system
│   ├── decision.py             # Decision making
│   ├── action.py               # Tool execution
│   ├── model_manager.py        # LLM management
│   └── tools.py                # Tool utilities
├── mcp_server_*.py             # MCP server implementations
├── documents/                   # Document storage for RAG
├── faiss_index/                # Vector database
└── pyproject.toml              # Dependencies
```

## 🧪 Testing

1. Start the Google Drive SSE server:
   ```bash
   python mcp_server_gdrive.py
   ```

2. Start the Telegram agent:
   ```bash
   python telegram_agent.py
   ```

3. Send a test message to your Telegram bot

4. Verify:
   - Agent receives the message
   - Creates Google Sheet
   - Returns sheet link in Telegram

## 📚 Dependencies

Key dependencies (see `pyproject.toml` for full list):
- `mcp[cli]` - Model Context Protocol
- `fastapi` + `uvicorn` - SSE server
- `python-telegram-bot` - Telegram integration
- `google-api-python-client` - Google APIs
- `faiss-cpu` - Vector database
- `pydantic` - Data validation
- `markitdown` + `pymupdf4llm` - Document parsing

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

[Add your license here]

## 🙏 Acknowledgments

- MCP (Model Context Protocol) for tool standardization
- Ollama for local LLM inference
- Google APIs for Sheets/Drive integration
- FastAPI for SSE transport layer

