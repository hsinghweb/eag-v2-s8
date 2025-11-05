# Server-Sent Events (SSE) - Complete Guide

## 📚 What is Server-Sent Events (SSE)?

**Server-Sent Events (SSE)** is an HTTP-based technology that enables a server to push data to a web client in real-time over a single, long-lived HTTP connection. It's a **unidirectional** communication protocol (server → client only).

### Key Characteristics

- ✅ **Unidirectional**: Server sends data to client, client cannot send data back
- ✅ **HTTP-based**: Uses standard HTTP protocol, no special protocol needed
- ✅ **Text-based**: Sends data as text/streaming text
- ✅ **Automatic Reconnection**: Built-in reconnection mechanism if connection drops
- ✅ **Simple**: Easier to implement than WebSockets
- ❌ **One-way**: Client cannot send data through the same connection
- ❌ **Text only**: No binary data support (though can encode binary as base64)

---

## 🔄 How SSE Works

### Basic Mechanism

```
┌─────────────┐                    ┌─────────────┐
│   Client    │                    │   Server    │
│  (Browser)  │                    │  (FastAPI)  │
└──────┬──────┘                    └──────┬──────┘
       │                                   │
       │ 1. HTTP GET Request              │
       │    Accept: text/event-stream     │
       ├─────────────────────────────────>│
       │                                   │
       │ 2. HTTP 200 OK                   │
       │    Content-Type: text/event-stream│
       │    Connection: keep-alive         │
       │<─────────────────────────────────┤
       │                                   │
       │ 3. Stream Events (data: ...)    │
       │<─────────────────────────────────┤
       │<─────────────────────────────────┤
       │<─────────────────────────────────┤
       │                                   │
       │ 4. Connection stays open         │
       │    Server sends when ready       │
       │<─────────────────────────────────┤
```

### HTTP Request Format

**Client Request:**
```http
GET /events HTTP/1.1
Host: example.com
Accept: text/event-stream
Cache-Control: no-cache
```

**Server Response:**
```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no

data: {"message": "Hello"}\n\n
data: {"message": "World"}\n\n
```

### SSE Event Format

Each event follows this format:
```
event: <event-type>
data: <data-line-1>
data: <data-line-2>
id: <event-id>
retry: <retry-timeout>

```

**Example:**
```
event: message
data: {"user": "Alice", "text": "Hello!"}
id: 12345
retry: 3000

```

**Rules:**
- Each line must end with `\n\n` (double newline)
- `data:` can appear multiple times (concatenated)
- `id:` is optional, used for reconnection
- `retry:` specifies milliseconds before reconnecting
- Empty line `\n\n` signals end of event

---

## 💻 SSE Implementation Examples

### Example 1: Basic SSE Server (FastAPI)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json
from datetime import datetime

app = FastAPI()

@app.get("/events")
async def stream_events():
    """Stream events to client"""
    async def event_generator():
        # Send initial connection message
        yield f"data: {json.dumps({'status': 'connected'})}\n\n"
        
        # Send periodic updates
        for i in range(10):
            await asyncio.sleep(1)  # Wait 1 second
            event_data = {
                "timestamp": datetime.now().isoformat(),
                "count": i + 1,
                "message": f"Event {i + 1}"
            }
            yield f"data: {json.dumps(event_data)}\n\n"
        
        # Send completion message
        yield f"data: {json.dumps({'status': 'completed'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# Run: uvicorn server:app --reload
```

### Example 2: SSE Client (JavaScript/Browser)

```javascript
// Create EventSource connection
const eventSource = new EventSource('http://localhost:8000/events');

// Listen for messages
eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
    
    // Update UI
    document.getElementById('status').innerHTML = 
        `Count: ${data.count} - ${data.message}`;
};

// Listen for specific event types
eventSource.addEventListener('custom-event', function(event) {
    console.log('Custom event:', event.data);
});

// Handle errors
eventSource.onerror = function(error) {
    console.error('SSE Error:', error);
    // EventSource automatically reconnects
};

// Close connection when done
// eventSource.close();
```

### Example 3: SSE Client (Python)

```python
import requests
import json

def stream_events(url):
    """Stream events from SSE endpoint"""
    response = requests.get(url, stream=True, headers={
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache'
    })
    
    buffer = ""
    for chunk in response.iter_content(chunk_size=1, decode_unicode=True):
        buffer += chunk
        
        # Check for complete event (ends with \n\n)
        if buffer.endswith('\n\n'):
            # Parse event
            lines = buffer.strip().split('\n')
            event_data = {}
            
            for line in lines:
                if line.startswith('data:'):
                    data = line[5:].strip()  # Remove 'data: ' prefix
                    try:
                        event_data = json.loads(data)
                    except:
                        event_data = {'raw': data}
            
            yield event_data
            buffer = ""  # Reset buffer

# Usage
for event in stream_events('http://localhost:8000/events'):
    print(f"Received: {event}")
```

### Example 4: Real-time Stock Prices (SSE)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json
import random

app = FastAPI()

# Simulated stock prices
stocks = {
    "AAPL": 150.00,
    "GOOGL": 2800.00,
    "MSFT": 350.00
}

@app.get("/stock-prices")
async def stream_stock_prices():
    """Stream real-time stock price updates"""
    async def price_updater():
        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
        
        while True:
            # Update stock prices (simulate)
            for symbol in stocks:
                # Random price change ±2%
                change = random.uniform(-0.02, 0.02)
                stocks[symbol] *= (1 + change)
                
                event = {
                    "symbol": symbol,
                    "price": round(stocks[symbol], 2),
                    "timestamp": asyncio.get_event_loop().time()
                }
                
                yield f"event: price_update\ndata: {json.dumps(event)}\n\n"
            
            await asyncio.sleep(1)  # Update every second
    
    return StreamingResponse(
        price_updater(),
        media_type="text/event-stream"
    )
```

**Client Usage:**
```javascript
const stockSource = new EventSource('http://localhost:8000/stock-prices');

stockSource.addEventListener('price_update', function(event) {
    const data = JSON.parse(event.data);
    console.log(`${data.symbol}: $${data.price}`);
    updateStockTable(data);  // Update UI
});
```

### Example 5: Progress Updates (SSE)

```python
@app.get("/task-progress/{task_id}")
async def stream_progress(task_id: str):
    """Stream progress updates for a long-running task"""
    async def progress_generator():
        total_steps = 100
        
        for step in range(total_steps + 1):
            # Simulate work
            await asyncio.sleep(0.1)
            
            progress = {
                "task_id": task_id,
                "step": step,
                "total": total_steps,
                "percentage": (step / total_steps) * 100,
                "status": "processing" if step < total_steps else "completed"
            }
            
            yield f"data: {json.dumps(progress)}\n\n"
    
    return StreamingResponse(
        progress_generator(),
        media_type="text/event-stream"
    )
```

**Client Usage:**
```javascript
const progressSource = new EventSource('/task-progress/12345');

progressSource.onmessage = function(event) {
    const progress = JSON.parse(event.data);
    document.getElementById('progress-bar').style.width = 
        progress.percentage + '%';
    document.getElementById('status').textContent = 
        `${progress.step}/${progress.total} - ${progress.status}`;
    
    if (progress.status === 'completed') {
        progressSource.close();
    }
};
```

---

## 🎯 When to Use SSE

### ✅ **Use SSE When:**

#### 1. **Real-time Notifications**
- **Example**: Push notifications, alerts, system events
- **Why**: Server needs to notify client immediately
- **Use Case**: "New message received", "Task completed", "System alert"

```python
# Example: Notification system
@app.get("/notifications")
async def stream_notifications():
    async def notify():
        while True:
            # Check for new notifications
            notification = await get_new_notification()
            if notification:
                yield f"data: {json.dumps(notification)}\n\n"
            await asyncio.sleep(1)
```

#### 2. **Live Data Feeds**
- **Example**: Stock prices, sports scores, weather updates
- **Why**: Data changes frequently, client needs latest values
- **Use Case**: Dashboard, live charts, monitoring

```python
# Example: Live dashboard data
@app.get("/dashboard-data")
async def stream_dashboard():
    async def update_dashboard():
        while True:
            metrics = await fetch_latest_metrics()
            yield f"data: {json.dumps(metrics)}\n\n"
            await asyncio.sleep(5)  # Update every 5 seconds
```

#### 3. **Progress Tracking**
- **Example**: File uploads, batch processing, data exports
- **Why**: User needs to see progress in real-time
- **Use Case**: "Processing 50% complete", "Uploading file..."

```python
# Example: File processing progress
@app.get("/process-progress/{job_id}")
async def stream_progress(job_id: str):
    async def track_progress():
        job = get_job(job_id)
        while not job.completed:
            yield f"data: {json.dumps(job.get_progress())}\n\n"
            await asyncio.sleep(0.5)
```

#### 4. **Server-to-Client Communication Only**
- **Example**: News feed, activity streams, log streaming
- **Why**: Client only needs to receive, not send
- **Use Case**: One-way data flow

#### 5. **Simple Implementation Needed**
- **Example**: Quick prototype, simple monitoring
- **Why**: Easier than WebSockets, no special protocol
- **Use Case**: Internal tools, simple dashboards

---

## ❌ **Don't Use SSE When:**

### 1. **Bidirectional Communication Needed**
- **Use Instead**: WebSockets
- **Example**: Chat applications, collaborative editing
- **Why**: SSE is one-way only

### 2. **Binary Data Required**
- **Use Instead**: WebSockets
- **Example**: Video streaming, file transfers
- **Why**: SSE is text-only (though can encode binary as base64)

### 3. **Low Latency Requirements**
- **Use Instead**: WebSockets
- **Example**: Real-time gaming, high-frequency trading
- **Why**: WebSockets have lower overhead

### 4. **Many Concurrent Connections**
- **Use Instead**: WebSockets or message queue
- **Example**: Thousands of clients
- **Why**: Each SSE connection uses HTTP keep-alive

### 5. **Client Needs to Send Data Frequently**
- **Use Instead**: WebSockets or HTTP polling
- **Example**: Interactive applications
- **Why**: SSE is server-to-client only

---

## 🔄 SSE vs Alternatives

### SSE vs WebSockets

| Feature | SSE | WebSockets |
|---------|-----|------------|
| **Direction** | Unidirectional (server → client) | Bidirectional |
| **Protocol** | HTTP | WS (separate protocol) |
| **Complexity** | Simple | More complex |
| **Data Format** | Text only | Binary + Text |
| **Reconnection** | Automatic | Manual |
| **Firewall** | Works through HTTP proxies | May be blocked |
| **Use Case** | Notifications, feeds | Chat, games |
| **Overhead** | HTTP headers | Lower overhead |

### SSE vs HTTP Polling

| Feature | SSE | HTTP Polling |
|---------|-----|--------------|
| **Latency** | Real-time | Delayed (poll interval) |
| **Efficiency** | One connection | Multiple requests |
| **Server Load** | Lower (persistent) | Higher (frequent requests) |
| **Battery** | Better (single connection) | Worse (many requests) |
| **Complexity** | Medium | Simple |

### SSE vs Long Polling

| Feature | SSE | Long Polling |
|---------|-----|--------------|
| **Connection** | Persistent | Recreated per request |
| **Latency** | Real-time | Request latency |
| **Efficiency** | Better | Good |
| **Reconnection** | Automatic | Manual |

---

## 🏗️ SSE in This Project (Google Sheets MCP Server)

### Why SSE is Used Here

**Note**: In this project, SSE is used as a **transport mechanism** for MCP (Model Context Protocol), not for true streaming events. The implementation uses HTTP GET/POST requests rather than streaming.

### Implementation

```python
# mcp_server_gdrive.py - FastAPI Server
@app.get("/mcp/tools")
async def list_tools():
    """List available tools"""
    return {"tools": [...]}

@app.post("/mcp/call_tool")
async def call_tool(request: ToolCallRequest):
    """Execute a tool"""
    tool_name = request.params.get("name")
    arguments = request.params.get("arguments", {})
    
    if tool_name == "create_google_sheet":
        result = await create_google_sheet(arguments)
    
    return {"result": result}  # Returns JSON, not streaming
```

### Why Not True SSE Streaming?

1. **Request-Response Pattern**: MCP tools are request-response based
2. **Tool Execution**: Tools execute and return results, not stream events
3. **Simplicity**: HTTP POST/GET is sufficient for tool calls
4. **Compatibility**: Works with existing MCP client infrastructure

### If We Used True SSE Streaming

```python
# Hypothetical streaming implementation
@app.get("/mcp/tools/stream")
async def stream_tool_updates():
    """Stream tool execution updates"""
    async def tool_updates():
        while True:
            # Check for tool execution status
            status = await get_tool_status()
            if status:
                yield f"data: {json.dumps(status)}\n\n"
            await asyncio.sleep(0.5)
    
    return StreamingResponse(
        tool_updates(),
        media_type="text/event-stream"
    )
```

**Use Case**: If we wanted to stream progress updates during long-running operations:
- "Creating sheet... 50%"
- "Adding data... 75%"
- "Getting link... 100%"

---

## 📊 Real-World SSE Use Cases

### 1. **Social Media Feed**
```python
@app.get("/feed")
async def stream_feed():
    """Stream new posts in real-time"""
    async def feed_updates():
        while True:
            new_post = await check_for_new_post()
            if new_post:
                yield f"data: {json.dumps(new_post)}\n\n"
            await asyncio.sleep(1)
```

### 2. **Live Chat (One-way)**
```python
@app.get("/chat/{room_id}/messages")
async def stream_messages(room_id: str):
    """Stream new messages to a chat room"""
    async def message_stream():
        last_message_id = 0
        while True:
            new_messages = await get_new_messages(room_id, last_message_id)
            for msg in new_messages:
                yield f"data: {json.dumps(msg)}\n\n"
                last_message_id = msg['id']
            await asyncio.sleep(0.5)
```

### 3. **System Monitoring**
```python
@app.get("/metrics")
async def stream_metrics():
    """Stream system metrics"""
    async def metric_updates():
        while True:
            metrics = {
                "cpu": get_cpu_usage(),
                "memory": get_memory_usage(),
                "disk": get_disk_usage(),
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json.dumps(metrics)}\n\n"
            await asyncio.sleep(2)
```

### 4. **Live Scoreboard**
```python
@app.get("/scores/{game_id}")
async def stream_scores(game_id: str):
    """Stream live game scores"""
    async def score_updates():
        while True:
            score = await get_latest_score(game_id)
            yield f"data: {json.dumps(score)}\n\n"
            await asyncio.sleep(1)
```

---

## ⚙️ Best Practices

### 1. **Error Handling**

```python
async def event_generator():
    try:
        while True:
            # Your event generation logic
            yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(1)
    except Exception as e:
        # Send error event
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
```

### 2. **Connection Management**

```python
# Client-side: Always close connections
const eventSource = new EventSource('/events');

// Close when component unmounts
window.addEventListener('beforeunload', () => {
    eventSource.close();
});
```

### 3. **Heartbeat**

```python
async def event_generator():
    while True:
        # Send heartbeat every 30 seconds
        yield f"event: heartbeat\ndata: {json.dumps({'time': time.time()})}\n\n"
        await asyncio.sleep(30)
```

### 4. **Event IDs for Reconnection**

```python
event_id = 0
async def event_generator():
    global event_id
    while True:
        event_id += 1
        yield f"id: {event_id}\ndata: {json.dumps(data)}\n\n"
```

### 5. **CORS Configuration**

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 🚀 Quick Start Guide

### 1. **Install Dependencies**

```bash
pip install fastapi uvicorn
```

### 2. **Create SSE Server**

```python
# server.py
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()

@app.get("/events")
async def stream_events():
    async def event_generator():
        for i in range(10):
            yield f"data: {json.dumps({'count': i})}\n\n"
            await asyncio.sleep(1)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### 3. **Run Server**

```bash
uvicorn server:app --reload
```

### 4. **Test with Client**

```javascript
// client.html
const source = new EventSource('http://localhost:8000/events');
source.onmessage = (e) => console.log(JSON.parse(e.data));
```

---

## 📝 Summary

**SSE is ideal for:**
- ✅ Real-time notifications
- ✅ Live data feeds
- ✅ Progress updates
- ✅ One-way server-to-client communication
- ✅ Simple implementation needs

**SSE is NOT ideal for:**
- ❌ Bidirectional communication
- ❌ Binary data
- ❌ Low-latency requirements
- ❌ Chat applications (use WebSockets)

**Key Takeaway**: SSE is perfect when you need **simple, one-way, real-time communication** from server to client. It's easier than WebSockets and more efficient than polling.

