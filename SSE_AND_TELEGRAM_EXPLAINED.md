# SSE (Server-Sent Events) and Telegram Communication Explained

This document explains:
1. **Where SSE is used** and how it works
2. **How the Agent listens and responds to Telegram messages**

---

## 🔄 SSE (Server-Sent Events) - Where and How

### What is SSE?

**Server-Sent Events (SSE)** is an HTTP-based transport layer that allows a server to push data to a client over a single HTTP connection. Unlike WebSockets, SSE is unidirectional (server → client) and uses standard HTTP, making it simpler for one-way communication.

### Where SSE is Used in This Project

SSE is used **exclusively for the Google Drive/Sheets MCP server** (`mcp_server_gdrive.py`).

#### Why SSE for Google Sheets?

1. **Remote Service**: Google Sheets operations need to run as a separate HTTP server
2. **Network Communication**: The agent needs to communicate with a remote service
3. **Standard HTTP**: SSE uses standard HTTP, making it easier to deploy and debug
4. **Streaming Support**: SSE supports streaming responses (though not fully utilized here)

### Architecture: SSE Implementation

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Process                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │         MultiMCP Session Manager                 │   │
│  │  ┌───────────────────────────────────────────┐  │   │
│  │  │         SSEClient (core/session.py)        │  │   │
│  │  │  - httpx.AsyncClient                       │  │   │
│  │  │  - HTTP GET/POST requests                  │  │   │
│  │  └───────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP Requests
                        │ (http://localhost:8002)
                        ↓
┌─────────────────────────────────────────────────────────┐
│          Google Drive SSE Server                        │
│          (mcp_server_gdrive.py)                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │         FastAPI Application                      │   │
│  │  - Port: 8002                                    │   │
│  │  - Endpoints:                                    │   │
│  │    • GET  /mcp/tools                            │   │
│  │    • POST /mcp/call_tool                        │   │
│  └─────────────────────────────────────────────────┘   │
│                          │                              │
│                          ↓                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │     Google Sheets/Drive API                     │   │
│  │  - create_google_sheet()                        │   │
│  │  - add_data_to_sheet()                          │   │
│  │  - get_sheet_link()                             │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### How SSE Works in This Project

#### 1. SSE Server Setup (`mcp_server_gdrive.py`)

```python
# FastAPI server runs on port 8002
app = FastAPI(title="Google Sheets/Drive MCP Server")

# Endpoint: List available tools
@app.get("/mcp/tools")
async def list_tools():
    return {"tools": [...]}  # Returns tool definitions

# Endpoint: Execute a tool
@app.post("/mcp/call_tool")
async def call_tool(request: ToolCallRequest):
    tool_name = request.params.get("name")
    arguments = request.params.get("arguments", {})
    
    if tool_name == "create_google_sheet":
        result = await create_google_sheet(arguments)
    # ... other tools
    
    return {"result": result}  # Returns JSON response
```

#### 2. SSE Client in Agent (`core/session.py`)

```python
class SSEClient:
    """Client for SSE-based MCP servers"""
    
    def __init__(self, params: SSEServerParameters):
        self.params = params
        # Uses httpx for async HTTP requests
        self.client = httpx.AsyncClient(timeout=params.timeout)
    
    async def list_tools(self):
        # GET request to list tools
        url = f"{self.params.base_url}/mcp/tools"
        response = await self.client.get(url)
        return response.json()
    
    async def call_tool(self, tool_name: str, arguments: dict):
        # POST request to execute tool
        url = f"{self.params.base_url}/mcp/call_tool"
        payload = {
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        response = await self.client.post(url, json=payload)
        return response.json()
```

#### 3. Configuration (`config/profiles.yaml`)

```yaml
mcp_servers:
  - id: gdrive
    transport: sse                    # ← SSE transport specified
    base_url: http://localhost:8002   # ← Server URL
```

#### 4. How Agent Uses SSE

```python
# In core/session.py - MultiMCP class
async def initialize(self):
    for server_config in self.server_configs:
        if server_config.get("transport") == "sse":
            # Create SSE client
            sse_params = SSEServerParameters(
                base_url=server_config.get("base_url")
            )
            sse_client = SSEClient(sse_params)
            self.sse_clients[server_config["id"]] = sse_client

async def call_tool(self, tool_name: str, arguments: dict):
    # Route to SSE client if tool belongs to SSE server
    if tool_name in self.sse_tools:
        sse_client = self.sse_clients[server_id]
        return await sse_client.call_tool(tool_name, arguments)
```

### SSE Communication Flow Example

**Example: Creating a Google Sheet**

1. **Agent calls tool**: `create_google_sheet|input.title="F1 Standings"`

2. **MultiMCP routes to SSE client**:
   ```python
   # Detects tool belongs to "gdrive" server (SSE)
   sse_client = self.sse_clients["gdrive"]
   ```

3. **SSE Client sends HTTP POST**:
   ```http
   POST http://localhost:8002/mcp/call_tool
   Content-Type: application/json
   
   {
     "method": "tools/call",
     "params": {
       "name": "create_google_sheet",
       "arguments": {
         "input": {"title": "F1 Standings"}
       }
     }
   }
   ```

4. **SSE Server processes request**:
   ```python
   # FastAPI endpoint receives request
   # Calls Google Sheets API
   # Returns result
   ```

5. **SSE Server responds**:
   ```json
   {
     "result": {
       "sheet_id": "1RIGSxzF-nb7wcjl_1d-n-FrSEMDRCMbPbuT3GdH-tlg",
       "sheet_url": "https://docs.google.com/spreadsheets/d/..."
     }
   }
   ```

6. **Agent receives result**:
   ```python
   # SSE client parses JSON response
   # Returns to agent loop
   # Agent continues workflow
   ```

### Why Not Use stdio for Google Sheets?

1. **Google API requires persistent connection**: OAuth tokens need to be managed
2. **FastAPI provides better HTTP handling**: Error handling, logging, middleware
3. **Separation of concerns**: Google Sheets server can run independently
4. **Scalability**: SSE server can be deployed separately

---

## 📱 Telegram Communication - How Agent Listens and Responds

### Overview

The Telegram integration uses **stdio transport** (not SSE). The agent communicates with Telegram via the Telegram Bot API, but the MCP server itself runs as a stdio subprocess.

### Architecture: Telegram Communication

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram Bot API                         │
│              (api.telegram.org/bot<TOKEN>)                  │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ HTTP GET/POST (Long Polling)
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│          Telegram MCP Server (stdio)                        │
│          (mcp_server_telegram.py)                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Tools:                                              │   │
│  │  • receive_telegram_message()                       │   │
│  │  • send_telegram_message()                          │   │
│  │                                                      │   │
│  │  Message Queue: _message_queue = []                  │   │
│  │  Processed IDs: _processed_message_ids = set()      │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │ MCP Protocol (stdio)
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│                    Agent Process                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         telegram_agent.py                            │   │
│  │  ┌───────────────────────────────────────────────┐  │   │
│  │  │  Main Loop:                                    │  │   │
│  │  │  1. Poll for messages (receive_telegram)      │  │   │
│  │  │  2. Process message (AgentLoop)                │  │   │
│  │  │  3. Send response (send_telegram_message)      │  │   │
│  │  └───────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### How Agent Listens to Telegram Messages

#### Step 1: Initialization (`telegram_agent.py`)

```python
async def poll_and_process():
    # 1. Load MCP server configs
    multi_mcp = MultiMCP(server_configs=mcp_servers)
    await multi_mcp.initialize()
    
    # 2. Initialize Telegram offset (skip old messages)
    init_response = await multi_mcp.call_tool("receive_telegram_message", {})
    # This calls the MCP server which acknowledges all pending updates
```

#### Step 2: Telegram Offset Initialization (`mcp_server_telegram.py`)

```python
def initialize_telegram_offset():
    """Initialize by fetching all pending updates and acknowledging them"""
    # Get all pending updates from Telegram
    updates_response = get_updates()  # No offset = get everything
    
    if updates_response.get("ok"):
        updates = updates_response.get("result", [])
        if updates:
            # Get highest update_id and mark all as processed
            max_update_id = max(update.get("update_id", 0) for update in updates)
            _last_update_id = max_update_id
            
            # Mark all old messages as processed
            for update in updates:
                _processed_update_ids.add(update.get("update_id"))
                message = update.get("message")
                if message:
                    _processed_message_ids.add(message.get("message_id"))
```

**Why this?** This ensures the agent only processes **NEW messages** sent after startup, not old messages in the queue.

#### Step 3: Message Polling Loop (`telegram_agent.py`)

```python
while True:
    # Poll for new messages
    response = await multi_mcp.call_tool("receive_telegram_message", {})
    
    # Parse response
    message = extract_message(response)
    chat_id = extract_chat_id(response)
    
    if message:
        # Process the message
        await process_message(message, chat_id, result_obj, multi_mcp)
```

#### Step 4: Telegram Polling (`mcp_server_telegram.py`)

```python
def poll_telegram_messages():
    """Poll Telegram for new messages and queue them"""
    # Use offset to skip old messages - only get updates after _last_update_id
    updates_response = get_updates(_last_update_id + 1)
    
    if updates_response.get("ok"):
        updates = updates_response.get("result", [])
        
        for update in updates:
            update_id = update.get("update_id")
            message = update.get("message")
            
            if message:
                text = message.get("text", "")
                chat_id = str(message.get("chat", {}).get("id"))
                message_id = message.get("message_id")
                
                # Skip if already processed
                if message_id in _processed_message_ids:
                    continue
                
                # Add to message queue
                _message_queue.append({
                    "message": text,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "update_id": update_id
                })
                
                # Mark as processed
                _processed_message_ids.add(message_id)
                _processed_update_ids.add(update_id)
```

#### Step 5: Message Retrieval (`mcp_server_telegram.py`)

```python
@mcp.tool()
def receive_telegram_message() -> TelegramMessageOutput:
    """Receive the latest message from Telegram bot"""
    # Poll for new messages
    poll_telegram_messages()
    
    # Return latest message from queue (FIFO)
    if _message_queue:
        msg = _message_queue.pop(0)  # Remove from queue
        return TelegramMessageOutput(
            message=msg["message"],
            chat_id=msg["chat_id"],
            message_id=msg["message_id"]
        )
    else:
        return TelegramMessageOutput(message="", chat_id="", message_id=0)
```

### How Agent Responds to Telegram Messages

#### Step 1: Process Message (`telegram_agent.py`)

```python
async def process_message(message: str, chat_id: str, result_obj: dict, multi_mcp):
    """Process a single Telegram message through the agent"""
    
    # Create agent loop with user's message
    agent = AgentLoop(
        user_input=message,
        dispatcher=multi_mcp
    )
    
    # Run agent cognitive loop
    final_response = await agent.run()
    # Agent performs: Search → Create Sheet → Add Data → Get Link
    
    # Extract sheet link from agent's memory
    sheet_link = extract_sheet_link(agent)
    
    # Build formatted Telegram response
    telegram_message = f"""✅ Task Completed Successfully!

📊 Your data has been organized in a Google Sheet.

🔗 Open the Sheet:
{sheet_link}

💡 You can view, edit, and share this sheet directly from the link above."""
```

#### Step 2: Send Response (`telegram_agent.py`)

```python
    # Send response back to Telegram
    await multi_mcp.call_tool("send_telegram_message", {
        "input": {
            "chat_id": chat_id,
            "text": telegram_message
        }
    })
```

#### Step 3: Telegram Sending (`mcp_server_telegram.py`)

```python
@mcp.tool()
def send_telegram_message(input: TelegramSendInput) -> str:
    """Send a message via Telegram bot"""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": input.chat_id,
        "text": input.text
    }
    
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    
    return f"Message sent successfully. Message ID: {result.get('message_id')}"
```

### Complete Message Flow Example

**User sends**: "Find the current point standings of F1 racers"

```
1. User sends message via Telegram app
   ↓
2. Telegram Bot API receives message
   ↓
3. Agent polls: receive_telegram_message()
   ↓
4. MCP server polls Telegram API: getUpdates(offset=_last_update_id + 1)
   ↓
5. Telegram API returns new message
   ↓
6. MCP server queues message in _message_queue
   ↓
7. Agent receives message from queue
   ↓
8. Agent processes: Search → Create Sheet → Add Data → Get Link
   ↓
9. Agent formats response with sheet link
   ↓
10. Agent sends: send_telegram_message(chat_id, response)
    ↓
11. MCP server calls Telegram API: sendMessage(chat_id, text)
    ↓
12. User receives formatted response with Google Sheet link
```

### Key Features

#### 1. **Message Deduplication**
- Uses `_processed_message_ids` set to track processed messages
- Prevents processing the same message twice
- Marks messages as processed immediately after queuing

#### 2. **Offset Management**
- Uses Telegram's `offset` parameter to skip old messages
- `_last_update_id` tracks the highest processed update_id
- Only fetches updates after `_last_update_id + 1`

#### 3. **Long Polling**
- Telegram API `getUpdates` uses `timeout=30` for long polling
- Reduces API calls by waiting for new messages
- More efficient than short polling

#### 4. **Queue Management**
- FIFO (First-In-First-Out) message queue
- Messages are queued as they arrive
- Agent processes messages one at a time

### Comparison: stdio vs SSE for Telegram

**Why stdio for Telegram?**
- ✅ Simple: Direct subprocess communication
- ✅ Fast: No network overhead
- ✅ Secure: Process isolation
- ✅ Stateless: Each call is independent

**Why NOT SSE for Telegram?**
- ❌ Telegram server doesn't need to be remote
- ❌ No streaming requirements
- ❌ Simpler with stdio for local operations

---

## 📊 Summary

### SSE Usage
- **Where**: Google Drive/Sheets MCP server only
- **Why**: Remote HTTP service for Google API operations
- **How**: FastAPI server on port 8002, HTTP GET/POST requests
- **Transport**: HTTP-based, async httpx client

### Telegram Communication
- **Transport**: stdio (local subprocess)
- **Listening**: Long polling via Telegram Bot API
- **Processing**: FIFO queue, deduplication, offset management
- **Responding**: HTTP POST to Telegram API's sendMessage endpoint

### Key Differences

| Feature | SSE (Google Sheets) | stdio (Telegram) |
|---------|---------------------|------------------|
| Transport | HTTP | Subprocess pipes |
| Server | FastAPI (port 8002) | Python subprocess |
| Communication | HTTP GET/POST | stdin/stdout JSON-RPC |
| Use Case | Remote service | Local tool |
| Deployment | Separate server | Same process |

---

## 🔍 Code Locations

- **SSE Server**: `mcp_server_gdrive.py`
- **SSE Client**: `core/session.py` → `SSEClient` class
- **Telegram Server**: `mcp_server_telegram.py`
- **Telegram Agent**: `telegram_agent.py`
- **MCP Session Manager**: `core/session.py` → `MultiMCP` class

---

This architecture allows the agent to seamlessly use both local tools (stdio) and remote services (SSE) while maintaining a consistent interface through the MCP protocol.

