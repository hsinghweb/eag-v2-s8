# Setup and Testing Guide

This guide walks you through setting up and testing the F1 Standings → Google Sheets → Gmail workflow via Telegram.

## Prerequisites

1. **Python 3.11+** with `uv` package manager
2. **Ollama** running locally on `http://localhost:11434`
3. Required Ollama models:
   - `nomic-embed-text` (for embeddings)
   - `gemma3:12b` or `gemma3:8b` (for image captioning)
   - `phi4` (for semantic chunking)
4. **Telegram Bot** (created via @BotFather)
5. **Google Cloud Project** with APIs enabled:
   - Gmail API
   - Google Sheets API
   - Google Drive API

---

## Step 1: Install Dependencies

```bash
# Install all dependencies
uv sync

# Or if using pip
pip install -r requirements.txt
```

---

## Step 2: Set Up Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow prompts to create your bot
4. Copy the bot token (e.g., `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
5. Save the token (you'll need it for `.env`)

**Optional**: Test your bot by sending a message to it on Telegram.

---

## Step 3: Set Up Google APIs

### 3.1 Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Note your project ID

### 3.2 Enable APIs

Enable these APIs in your project:
- **Gmail API**
- **Google Sheets API**
- **Google Drive API**

### 3.3 Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: `EAG Agent` (or any name)
5. Click **Create**
6. Download the JSON file
7. Save it as:
   - `gmail_credentials.json` (for Gmail)
   - `credentials.json` (for Sheets/Drive - you can use the same file)

### 3.4 Run OAuth Flow (First Time)

For **Gmail**:
```bash
python -c "
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.send']
flow = InstalledAppFlow.from_client_secrets_file('gmail_credentials.json', SCOPES)
creds = flow.run_local_server(port=0)
with open('gmail_token.json', 'w') as token:
    token.write(creds.to_json())
print('✅ Gmail token saved')
"
```

For **Google Sheets/Drive**:
```bash
python -c "
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=0)
with open('token.json', 'w') as token:
    token.write(creds.to_json())
print('✅ Google Sheets/Drive token saved')
"
```

**Note**: A browser window will open for you to authorize the app. Make sure you're signed in to the Google account you want to use.

---

## Step 4: Configure Environment Variables

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` and add your credentials:
```env
TELEGRAM_BOT_TOKEN=your_actual_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here  # If using Gemini
```

**Note**: The Google API credentials files (`gmail_credentials.json`, `credentials.json`, `gmail_token.json`, `token.json`) should be in the project root directory.

---

## Step 5: Start the Google Sheets/Drive SSE Server

The Google Sheets/Drive server runs as an SSE (HTTP) server. Start it in a separate terminal:

```bash
python mcp_server_gdrive.py
```

You should see:
```
🚀 Starting Google Sheets/Drive MCP Server (SSE) on port 8002
📋 MCP endpoint: http://localhost:8002/mcp/tools
```

**Keep this terminal running!**

---

## Step 6: Verify Ollama Models

Make sure Ollama is running and has the required models:

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Install missing models
ollama pull nomic-embed-text
ollama pull gemma3:12b
ollama pull phi4
```

---

## Step 7: Test the Complete Workflow

### 7.1 Start the Agent

In a **new terminal**, run:
```bash
python agent.py
```

The agent will:
1. Load all MCP servers (including Telegram, Gmail, and Google Sheets/Drive)
2. Wait for input

### 7.2 Send Telegram Message

**Option A: Manual Polling** (for testing)

In another terminal, test Telegram polling:
```bash
python -c "
import sys
sys.path.insert(0, '.')
from mcp_server_telegram import poll_telegram_messages
poll_telegram_messages()
"
```

**Option B: Send Message via Telegram App**

1. Open Telegram app
2. Search for your bot (by the username you created)
3. Send the message: **"Find the Current Point Standings of F1 Racers"**
4. The message will be queued for the agent

### 7.3 Agent Workflow

The agent should:
1. **Receive Telegram message** via `receive_telegram_message()` tool
2. **Search for F1 standings** using the `search` tool (from `mcp_server_3.py`)
3. **Create Google Sheet** via `create_google_sheet()` (from SSE server)
4. **Add F1 data** to sheet via `add_data_to_sheet()`
5. **Get sheet link** via `get_sheet_link()` or `share_sheet()`
6. **Send email** with link via `send_email_with_link()` (from Gmail server)

### 7.4 Expected Output

You should see:
- Agent logs showing tool calls
- Google Sheet created in your Google Drive
- Email sent to your Gmail with the sheet link
- Final answer from the agent

---

## Step 8: Verification Checklist

- [ ] Agent receives Telegram message correctly
- [ ] F1 standings data is fetched
- [ ] Google Sheet is created (check Google Drive)
- [ ] Data appears in the sheet correctly
- [ ] Email is received in Gmail inbox
- [ ] Email contains working link to Google Sheet
- [ ] Sheet link opens correctly

---

## Troubleshooting

### Telegram Bot Not Responding

- Verify `TELEGRAM_BOT_TOKEN` is correct in `.env`
- Make sure you've started a conversation with the bot first
- Check that `receive_telegram_message()` is being called

### Google API Errors

- Verify `credentials.json` and `token.json` exist
- Check that APIs are enabled in Google Cloud Console
- Re-run OAuth flow if tokens expired
- Ensure you're using the correct Google account

### SSE Server Connection Issues

- Verify `mcp_server_gdrive.py` is running on port 8002
- Test with: `curl http://localhost:8002/mcp/tools`
- Check firewall/port blocking

### Agent Can't Find Tools

- Check `config/profiles.yaml` has correct server configs
- Verify all server scripts exist and are executable
- Check transport type matches (stdio vs sse)

---

## Advanced: Testing Individual Components

### Test Telegram Server

```bash
python mcp_server_telegram.py dev
# Then use MCP inspector or test manually
```

### Test Google Sheets/Drive Server

```bash
# Start server
python mcp_server_gdrive.py

# In another terminal, test tools
curl http://localhost:8002/mcp/tools
```

### Test Gmail Server

```bash
python mcp_server_gmail.py dev
```

---

## Notes

- The Google Sheets/Drive server must be running before starting the agent (it's an SSE server)
- Telegram polling happens when `receive_telegram_message()` is called
- For production, consider using webhooks instead of polling for Telegram
- Keep your `.env` and credential files secure - never commit them to git!

---

## Next Steps After Testing

Once everything works:
1. Consider adding webhook support for Telegram (instead of polling)
2. Add error handling and retries
3. Add logging to file
4. Consider rate limiting for API calls
5. Add screenshot/video upload to LMS (if required)

