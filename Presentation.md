# Cortex-R: Intelligent Agentic AI System
## Presentation Document

---

## 🎯 The Idea

**Cortex-R** is an intelligent agentic AI system that combines Large Language Models (LLMs) with external tools and memory to solve complex, multi-step tasks autonomously. The system can:

- **Receive queries via Telegram** and process them intelligently
- **Search the web** for real-time information
- **Organize data** in Google Sheets automatically
- **Respond with formatted results** including direct links to created resources

### Key Innovation

Unlike traditional chatbots, Cortex-R uses a **5-phase cognitive loop** that mimics human reasoning:
1. **Perceives** the user's intent
2. **Retrieves** relevant context from memory
3. **Plans** the execution steps
4. **Executes** tools via MCP protocol
5. **Completes** with a formatted response

### Use Cases

- **Data Research**: "Find top 10 F1 racers' current standings"
- **Information Gathering**: "Get latest AI research papers"
- **Data Organization**: Automatically creates structured Google Sheets
- **Real-time Queries**: Search and organize current information

---

## 🔄 Agent Workflow

### High-Level Flow

```
User sends message via Telegram
    ↓
Agent receives message
    ↓
┌─────────────────────────────────────┐
│  PHASE 1: PERCEPTION                │
│  - Extract intent, entities          │
│  - Detect scope limits (top 10, etc)│
│  - Identify tool hints               │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  PHASE 2: MEMORY                    │
│  - Search FAISS vector store         │
│  - Retrieve relevant context         │
│  - Build context for decision        │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  PHASE 3: DECISION                  │
│  - Generate execution plan           │
│  - Select appropriate tools          │
│  - Create workflow steps             │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  PHASE 4: EXECUTION                 │
│  - Execute tools via MCP             │
│  - Handle tool results               │
│  - Update memory                     │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  PHASE 5: COMPLETION                │
│  - Extract final answer              │
│  - Get Google Sheet link             │
│  - Send formatted response          │
└─────────────────────────────────────┘
    ↓
User receives response with sheet link
```

### Detailed Workflow Example

**User Query**: "Find the current point standings of F1 racers"

1. **Perception**
   - Intent: "Find standings"
   - Entities: ["F1", "racers", "standings"]
   - Scope: top 10 (default)
   - Tool Hint: "search"

2. **Memory**
   - Retrieves relevant past queries about standings
   - No relevant context → proceed to search

3. **Decision**
   - Plan: `search → create_google_sheet → add_data_to_sheet → get_sheet_link → FINAL_ANSWER`

4. **Execution**
   - **Step 1**: `search` tool → Gets F1 standings data
   - **Step 2**: `create_google_sheet` → Creates spreadsheet
   - **Step 3**: `add_data_to_sheet` → Adds top 10 racers with points
   - **Step 4**: `get_sheet_link` → Retrieves shareable URL

5. **Completion**
   - Extracts sheet link from memory
   - Formats Telegram response with link
   - Sends response to user

### Workflow Guarantees

- **Mandatory Steps**: Search → Create Sheet → Add Data → Get Link
- **Error Handling**: Retry logic with exponential backoff
- **Loop Prevention**: Detects repeated tool calls
- **Completion Guarantee**: Always returns `FINAL_ANSWER`

---

## 🧪 How to Test It

### Prerequisites Setup

1. **Install Ollama Models**
   ```bash
   ollama pull nomic-embed-text
   ollama pull phi3:mini
   ```

2. **Configure Environment**
   Create `.env` file:
   ```env
   TELEGRAM_BOT_TOKEN=your_bot_token
   GMAIL_ADDRESS=your_email@gmail.com
   GMAIL_APP_PASSWORD=your_app_password
   RECIPIENT_EMAIL=recipient@gmail.com
   GOOGLE_DRIVE_CREDENTIALS_JSON=path/to/credentials.json
   GOOGLE_SHEETS_CREDENTIALS_JSON=path/to/credentials.json
   GEMINI_API_KEY=your_gemini_key
   ```

3. **Set up Google OAuth**
   ```bash
   python setup_google_oauth.py
   ```

### Testing Steps

#### Step 1: Start the Google Drive SSE Server

```bash
python mcp_server_gdrive.py
```

Expected output:
```
Starting FastAPI server on http://localhost:8002
Google Drive SSE server ready
```

#### Step 2: Start the Telegram Agent

```bash
python telegram_agent.py
```

Expected output:
```
🧠 Cortex-R Telegram Agent Ready
📱 Initializing Telegram - skipping old messages...
✅ Telegram initialized. Agent will only process NEW messages sent after this point.
🔄 Agent is now idle, waiting for NEW messages...
💬 Send a NEW message to your bot to start processing
```

#### Step 3: Send a Test Message

Via Telegram, send to your bot:
```
Find the current point standings of F1 racers
```

#### Step 4: Observe the Agent

The agent will:
1. ✅ Receive the message
2. ✅ Search for F1 standings
3. ✅ Create Google Sheet
4. ✅ Add data (top 10 racers)
5. ✅ Get sheet link
6. ✅ Send response with link

#### Step 5: Verify Results

- Check Telegram for the formatted response with Google Sheet link
- Click the link to verify the sheet was created with correct data

### Test Scenarios

**Scenario 1: Basic Query**
- Query: "Find top 10 trending stocks"
- Expected: Sheet with stock data, link in Telegram

**Scenario 2: Scope Limit**
- Query: "Get current weather for top 5 cities"
- Expected: Sheet with 5 cities, respects scope limit

**Scenario 3: Error Handling**
- Query: "Find nonexistent data"
- Expected: Graceful error message, no crash

---

## 🏗️ Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface Layer                      │
│  ┌──────────────┐              ┌──────────────┐           │
│  │   Telegram   │              │   CLI (API)  │           │
│  └──────┬───────┘              └──────┬───────┘           │
└─────────┼─────────────────────────────┼─────────────────────┘
          │                             │
          └─────────────┬───────────────┘
                        │
          ┌─────────────▼─────────────┐
          │    Agent Cognitive Loop    │
          │  ┌──────────────────────┐ │
          │  │  Perception Module    │ │
          │  │  Memory Module       │ │
          │  │  Decision Module     │ │
          │  │  Action Module       │ │
          │  └──────────────────────┘ │
          └─────────────┬───────────────┘
                        │
          ┌─────────────▼───────────────┐
          │    MCP Session Manager       │
          │  ┌──────────┐  ┌──────────┐ │
          │  │  Stdio   │  │   SSE    │ │
          │  │ Clients  │  │  Client  │ │
          │  └──────────┘  └──────────┘ │
          └─────────────┬───────────────┘
                        │
    ┌───────────────────┼───────────────────┐
    │                   │                   │
┌───▼────┐        ┌────▼────┐      ┌──────▼──────┐
│ Stdio │        │   SSE   │      │   Memory    │
│ MCP   │        │   MCP   │      │   (FAISS)   │
│Servers│        │ Server  │      │             │
└───────┘        └─────────┘      └─────────────┘
```

### Component Architecture

#### 1. Core Layer (`core/`)

**`loop.py`** - Main Cognitive Loop
- 5-phase workflow orchestration
- Error handling and retry logic
- Loop detection and prevention
- Completion guarantees

**`session.py`** - MCP Session Management
- MultiMCP client for multiple servers
- Stdio transport support
- SSE (HTTP) transport support
- Tool discovery and routing

**`context.py`** - Context Management
- Session state tracking
- Memory trace management
- Agent profile configuration

**`strategy.py`** - Strategy & Planning
- Workflow guidance generation
- Tool selection logic
- Plan validation

#### 2. Cognitive Modules (`modules/`)

**`perception.py`**
- LLM-based intent extraction
- Entity recognition
- Scope limit detection
- Tool hint generation

**`memory.py`**
- FAISS vector store integration
- Semantic search
- Context retrieval
- Memory item management

**`decision.py`**
- Plan generation using LLM
- Workflow step definition
- Tool selection guidance

**`action.py`**
- Tool execution
- Result parsing
- Error handling

**`model_manager.py`**
- LLM model abstraction
- Gemini API integration
- Ollama integration
- Retry logic with exponential backoff

#### 3. MCP Servers

**Stdio Servers** (Local Process Communication)
- `mcp_server_1.py`: Math operations
- `mcp_server_2.py`: Document processing, RAG
- `mcp_server_3.py`: Web search
- `mcp_server_telegram.py`: Telegram integration
- `mcp_server_gmail.py`: Email sending (SMTP)

**SSE Server** (HTTP Server-Sent Events)
- `mcp_server_gdrive.py`: Google Sheets/Drive (FastAPI on port 8002)

### Data Flow

```
User Input
    ↓
Perception → Extract Intent/Entities/Scope
    ↓
Memory → Retrieve Context (FAISS)
    ↓
Decision → Generate Plan (LLM)
    ↓
Action → Execute Tools (MCP)
    ↓
Memory → Store Results (FAISS)
    ↓
Completion → Format Response
    ↓
User Output
```

### Transport Layers

**Stdio Transport**
- Local process communication
- Fast, secure, no network overhead
- Used for: Math, Documents, Web Search, Telegram, Gmail

**SSE Transport (Server-Sent Events)**
- HTTP-based, networked communication
- Streaming responses
- Used for: Google Drive/Sheets (remote server)

---

## 🛠️ Technology Stack

### Core Technologies

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Language** | Python 3.11+ | Core implementation |
| **LLM Framework** | MCP (Model Context Protocol) | Tool standardization |
| **LLM API** | Google Gemini 2.0 Flash | Text generation |
| **Embeddings** | Nomic Embed Text | Vector embeddings |
| **Vector DB** | FAISS (CPU) | Semantic search |
| **Web Framework** | FastAPI + Uvicorn | SSE server |
| **HTTP Client** | httpx | Async HTTP requests |
| **Telegram** | python-telegram-bot | Bot integration |
| **Google APIs** | google-api-python-client | Sheets/Drive |
| **Email** | smtplib (Python stdlib) | SMTP email |
| **Document Parsing** | MarkItDown, PyMuPDF4LLM | PDF/HTML parsing |
| **Data Validation** | Pydantic | Schema validation |
| **Configuration** | YAML, JSON | Config files |

### Key Libraries

```python
# Core Framework
mcp[cli]>=1.6.0              # Model Context Protocol
pydantic>=2.11.3             # Data validation

# LLM & Embeddings
llama-index>=0.12.31         # LLM framework
google-genai                 # Gemini API

# Vector Database
faiss-cpu>=1.10.0            # Vector similarity search

# Web & HTTP
fastapi>=0.104.0             # Web framework
uvicorn>=0.24.0              # ASGI server
httpx>=0.28.1                # Async HTTP client

# Telegram
python-telegram-bot>=20.7    # Telegram Bot API

# Google APIs
google-api-python-client>=2.100.0  # Google Services
google-auth>=2.23.0                 # OAuth2

# Document Processing
markitdown[all]>=0.1.1       # HTML to Markdown
pymupdf4llm>=0.0.21         # PDF parsing

# Utilities
python-dotenv>=1.0.0        # Environment variables
pydantic-settings>=2.1.0    # Settings management
```

### Infrastructure

- **Local LLM**: Ollama (for embeddings and semantic chunking)
- **Cloud LLM**: Google Gemini API (for text generation)
- **Storage**: Local FAISS index, Google Drive
- **Communication**: Telegram Bot API, SMTP (Gmail)

---

## 🤖 LLM Models Used

### Primary Models

#### 1. **Gemini 2.0 Flash** (Text Generation)
- **Provider**: Google Cloud
- **Purpose**: Main text generation for perception, decision, and planning
- **API**: REST API via `google-genai`
- **Features**:
  - Fast inference
  - High-quality reasoning
  - JSON output support
  - Rate limit handling with retry logic

**Usage**:
- Perception: Intent extraction, entity recognition
- Decision: Plan generation, workflow guidance
- General: Text generation tasks

#### 2. **Nomic Embed Text v1** (Embeddings)
- **Provider**: Ollama (local)
- **Purpose**: Vector embeddings for semantic search
- **Model**: `nomic-embed-text`
- **Dimension**: 768
- **Features**:
  - High-quality embeddings
  - Fast local inference
  - No API costs

**Usage**:
- Document embeddings for RAG
- Query embeddings for semantic search
- Memory context retrieval

#### 3. **Phi3 Mini** (Semantic Chunking)
- **Provider**: Ollama (local)
- **Purpose**: Topic-based document chunking
- **Model**: `phi3:mini`
- **Features**:
  - Lightweight (3B parameters)
  - Fast inference
  - Good for classification tasks

**Usage**:
- Semantic chunking of documents
- Topic boundary detection
- Document preprocessing

### Model Configuration

**Location**: `config/models.json`

```json
{
  "defaults": {
    "text_generation": "gemini",
    "embedding": "nomic"
  },
  "models": {
    "gemini": {
      "type": "gemini",
      "model": "gemini-2.0-flash",
      "api_key_env": "GEMINI_API_KEY"
    },
    "nomic": {
      "type": "huggingface",
      "model": "nomic-ai/nomic-embed-text-v1",
      "embedding_dimension": 768
    }
  }
}
```

### Model Selection Rationale

1. **Gemini 2.0 Flash**
   - Fast response times
   - Good JSON output
   - Free tier available
   - Reliable API

2. **Nomic Embed Text**
   - State-of-the-art embeddings
   - Open-source
   - Local inference (privacy)
   - No API costs

3. **Phi3 Mini**
   - Small model (3B parameters)
   - Fast chunking
   - Good topic detection
   - Efficient for preprocessing

### Model Usage Flow

```
User Query
    ↓
[Gemini] → Perception (intent, entities, scope)
    ↓
[Nomic] → Embed Query → FAISS Search
    ↓
[Gemini] → Decision (plan generation)
    ↓
Tool Execution
    ↓
[Nomic] → Embed Results → Store in FAISS
    ↓
[Gemini] → Final Answer Formatting
```

### Rate Limiting & Retry Logic

- **Gemini API**: Exponential backoff for 429 errors
- **Retry Strategy**: Up to 3 attempts with increasing delays
- **Error Handling**: Graceful fallbacks and error messages

---

## 📊 Key Features Summary

✅ **Multi-Modal Tool Integration** (stdio + SSE)  
✅ **Telegram Bot Interface**  
✅ **Google Sheets Automation**  
✅ **RAG with Semantic Search**  
✅ **Intelligent Workflow Planning**  
✅ **Error Handling & Retry Logic**  
✅ **Memory-Aware Context**  
✅ **Scope Limit Detection**  
✅ **Generic Query Processing**  

---

## 🎓 Learning Outcomes

This project demonstrates:

1. **Agentic AI Architecture**: Multi-phase cognitive loop
2. **MCP Protocol**: Standardized tool communication
3. **Transport Layers**: stdio vs SSE implementations
4. **RAG Implementation**: Vector search and semantic chunking
5. **LLM Integration**: Multiple models for different tasks
6. **Error Resilience**: Robust error handling strategies
7. **Real-World Integration**: Telegram, Google APIs, SMTP

---

## 📞 Contact & Support

For questions, issues, or contributions, please refer to the project repository.

---

**Built with ❤️ using MCP, Gemini, Ollama, and modern Python technologies**

