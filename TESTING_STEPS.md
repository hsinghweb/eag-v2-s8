# Complete Testing Guide

This guide walks you through testing the generic agent workflow with Telegram integration.

## Prerequisites Checklist

Before testing, ensure you have:

- [ ] Python 3.11+ installed
- [ ] `uv` package manager installed
- [ ] Ollama running locally on `http://localhost:11434`
- [ ] Required Ollama models installed:
  - [ ] `nomic-embed-text` (for embeddings)
  - [ ] `phi3:mini` (for semantic chunking)
  - [ ] `gemma2:2b` (optional, for image captioning)
- [ ] Telegram bot created via @BotFather
- [ ] Google Cloud Project with APIs enabled:
  - [ ] Gmail API
  - [ ] Google Sheets API
  - [ ] Google Drive API
- [ ] OAuth credentials files:
  - [ ] `gmail_credentials.json` (for Gmail)
  - [ ] `credentials.json` (for Google Sheets/Drive)
  - [ ] `gmail_token.json` (generated after first OAuth)
  - [ ] `token.json` (generated after first OAuth)
- [ ] `.env` file configured with:
  - [ ] `TELEGRAM_BOT_TOKEN=your_bot_token`
  - [ ] `GMAIL_USER_EMAIL=your-email@gmail.com`
  - [ ] `GEMINI_API_KEY=your_key` (if using Gemini)

---

## Step 1: Verify Ollama Models

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Install required models if not already installed
ollama pull nomic-embed-text
ollama pull phi3:mini
ollama pull gemma2:2b  # Optional
```

**Expected Output:**
```
pulling manifest
pulling 8a2b3c4d...
success
```

---

## Step 2: Verify Environment Variables

```bash
# Check if .env file exists and has required variables
cat .env
```

**Expected Content:**
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
GMAIL_USER_EMAIL=your-email@gmail.com
GEMINI_API_KEY=your_gemini_api_key  # If using Gemini
```

**If `.env` doesn't exist:**
```bash
# Create .env file
echo "TELEGRAM_BOT_TOKEN=your_bot_token_here" >> .env
echo "GMAIL_USER_EMAIL=your-email@gmail.com" >> .env
```

---

## Step 3: Verify Google OAuth Credentials

```bash
# Check if credential files exist
ls -la gmail_credentials.json credentials.json

# Check if token files exist (will be created after first OAuth)
ls -la gmail_token.json token.json
```

**If credentials are missing:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create OAuth 2.0 credentials
3. Download and save as:
   - `gmail_credentials.json` (for Gmail)
   - `credentials.json` (for Google Sheets/Drive)

**If tokens are missing:**
Run the OAuth flow:
```bash
python setup_google_oauth.py
```

---

## Step 4: Start the Google Sheets/Drive SSE Server

**Open Terminal 1:**

```bash
# Navigate to project directory
cd /path/to/eag-v2-s8

# Start the SSE server
python mcp_server_gdrive.py
```

**Expected Output:**
```
🚀 Starting Google Sheets/Drive MCP Server (SSE) on port 8002
📋 MCP endpoint: http://localhost:8002/mcp/tools
✅ Google Sheets/Drive services initialized
INFO:     Uvicorn running on http://0.0.0.0:8002
```

**Keep this terminal running!**

---

## Step 5: Start the Telegram Agent

**Open Terminal 2:**

```bash
# Navigate to project directory
cd /path/to/eag-v2-s8

# Start the Telegram agent
python telegram_agent.py
```

**Expected Output:**
```
🧠 Cortex-R Telegram Agent Ready
📱 Polling Telegram for messages...
💬 Send a message to your bot to start processing
Agent before initialize
✅ MCP servers initialized
✅ All MCP servers connected
```

**Keep this terminal running!**

---

## Step 6: Test the Workflow

### Test 1: Generic Standings Query (Default Top 10)

1. **Open Telegram** and find your bot
2. **Send message:** `"Find the Current Point Standings of F1 Racers"`

**Expected Behavior:**
- Agent receives message
- Performs search with "top 10" scope
- Creates Google Sheet titled "F1 Standings" (or similar)
- Extracts top 10 drivers with points
- Gets sheet link
- Sends email to `GMAIL_USER_EMAIL` from `.env`

**Expected Terminal Output (Terminal 2):**
```
📩 Received Telegram message: Find the Current Point Standings of F1 Racers
[agent] Starting session: session-1234567890-abc123
[loop] Step 1 of 10
[perception] Intent: Find current point standings, Hint: search, Scope: top 10 (top)
[memory] Retrieved 0 memories
[plan] FUNCTION_CALL: search|query="F1 current point standings 2024 top 10"
[action] search → [Search results...]
[loop] Step 2 of 10
[plan] FUNCTION_CALL: create_google_sheet|input.title="F1 Standings"
[action] create_google_sheet → {"sheet_id": "abc123...", "sheet_url": "https://..."}
[loop] Step 3 of 10
[plan] FUNCTION_CALL: add_data_to_sheet|input.sheet_id="abc123..."|input.data=[["Driver","Points"],...]
[action] add_data_to_sheet → {"success": true, "updated_cells": 11}
[loop] Step 4 of 10
[plan] FUNCTION_CALL: get_sheet_link|input.sheet_id="abc123..."
[action] get_sheet_link → {"link": "https://docs.google.com/spreadsheets/d/..."}
[loop] Step 5 of 10
[plan] FUNCTION_CALL: send_email_with_link|to="your-email@gmail.com"|subject="F1 Standings"|...
[action] send_email_with_link → {"success": true, "message_id": "msg123"}
[loop] Step 6 of 10
[plan] FINAL_ANSWER: [Task completed. Sheet created at https://... and emailed to your-email@gmail.com]

💡 Final Answer:
Task completed. Sheet created at https://docs.google.com/spreadsheets/d/... and emailed to your-email@gmail.com
```

**Expected Telegram Response:**
```
✅ Task Completed!

Task completed. Sheet created at https://docs.google.com/spreadsheets/d/... and emailed to your-email@gmail.com
```

**Verify:**
- [ ] Google Sheet created in Google Drive
- [ ] Sheet contains headers: "Driver", "Points"
- [ ] Sheet contains exactly 10 rows of data (top 10 drivers)
- [ ] Email received at `GMAIL_USER_EMAIL` with sheet link
- [ ] Email subject matches query topic

---

### Test 2: Explicit Top 20 Query

1. **Send message:** `"Find top 20 cricket players"`

**Expected Behavior:**
- Agent detects `scope_limit: 20`
- Searches with "top 20" scope
- Creates sheet with "Cricket Players" or similar title
- Extracts exactly 20 rows of data
- Sends email with sheet link

**Verify:**
- [ ] Sheet contains exactly 20 rows of data
- [ ] Search query includes "top 20"

---

### Test 3: Generic Query (No Specific Domain)

1. **Send message:** `"Find current stock prices"`

**Expected Behavior:**
- Agent detects `scope_limit: 10` (default for "current")
- Creates generic sheet title from query
- Extracts relevant data (not F1-specific)
- Works with any data type

**Verify:**
- [ ] Sheet title is relevant to query (not "F1 Standings")
- [ ] Data extracted matches query type
- [ ] Headers are appropriate for data type

---

### Test 4: Different Query Type

1. **Send message:** `"Find latest weather data"`

**Expected Behavior:**
- Agent works generically (not tied to standings/rankings)
- Creates appropriate sheet structure
- Extracts weather data appropriately

**Verify:**
- [ ] Sheet contains weather-related data
- [ ] Headers match data type (e.g., ["Location","Temperature","Condition"])

---

## Step 7: Verify Results

### Check Google Drive

1. Go to [Google Drive](https://drive.google.com)
2. Look for newly created sheets:
   - Sheet titles should match query topics
   - Sheets should contain data with proper headers
   - Data should be limited to scope_limit (if set)

### Check Gmail

1. Go to [Gmail](https://mail.google.com)
2. Check inbox for emails from your bot
3. Verify:
   - Email subject matches query topic
   - Email body mentions the data type
   - Sheet link is clickable and works

### Check Terminal Output

1. **Terminal 1 (SSE Server):** Should show:
   - Tool calls being received
   - No errors

2. **Terminal 2 (Telegram Agent):** Should show:
   - Complete workflow execution
   - No errors or loops
   - Final answer with summary

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'X'"

**Solution:**
```bash
# Install dependencies
uv sync

# Or with pip
pip install -r requirements.txt
```

---

### Issue: "Error 403: access_denied" during OAuth

**Solution:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services** → **OAuth consent screen**
3. Add your email as a **Test user**
4. Try OAuth flow again

---

### Issue: "Tool execution failed: object of type 'NoneType' has no len()"

**Solution:**
- Ensure Google Sheets/Drive SSE server is running (Terminal 1)
- Check that `token.json` exists and is valid
- Verify Google APIs are enabled in Cloud Console

---

### Issue: "SSE call_tool error: Connection refused"

**Solution:**
- Ensure SSE server is running on port 8002
- Check `config/profiles.yaml` has correct `base_url: http://localhost:8002`

---

### Issue: "No credentials available on startup"

**Solution:**
- Run OAuth flow: `python setup_google_oauth.py`
- Ensure credential files are in project root
- Check file names match: `gmail_credentials.json`, `credentials.json`

---

### Issue: Agent loops without completing

**Solution:**
- Check `max_steps` in `config/profiles.yaml` (should be 10)
- Verify search results are being retrieved
- Check that sheet_id is being extracted correctly

---

### Issue: Email not sent or wrong email used

**Solution:**
- Verify `.env` has `GMAIL_USER_EMAIL=your-email@gmail.com`
- Check that email in `.env` matches OAuth account
- Ensure Gmail API is enabled in Cloud Console

---

### Issue: "Error: pull model manifest: file does not exist"

**Solution:**
- Use correct model names:
  - `nomic-embed-text` (not `nomic-embed`)
  - `phi3:mini` (not `phi3` or `llama3.2:1b-instruct`)
  - `gemma2:2b` (not `llava:3.8b`)

---

## Success Criteria

✅ **All tests pass if:**
- Agent receives Telegram messages
- Search queries are enhanced with scope limits
- Google Sheets are created with relevant titles
- Data is extracted and limited to scope_limit
- Emails are sent to `GMAIL_USER_EMAIL` from `.env`
- Sheet links work and contain correct data
- No F1-specific hardcoding in prompts
- Workflow works for any query type

---

## Next Steps

After successful testing:
1. Test with various query types (sports, stocks, weather, etc.)
2. Verify scope limiting works correctly
3. Confirm email always uses `.env` address
4. Test edge cases (no scope, "all", etc.)

---

## Quick Test Checklist

- [ ] Ollama models installed
- [ ] `.env` file configured
- [ ] Google OAuth credentials set up
- [ ] SSE server running (Terminal 1)
- [ ] Telegram agent running (Terminal 2)
- [ ] Test query sent via Telegram
- [ ] Sheet created in Google Drive
- [ ] Email received with sheet link
- [ ] Data limited to scope_limit
- [ ] No errors in terminals

---

**Need Help?**
- Check terminal output for error messages
- Verify all prerequisites are met
- Review `GENERIC_WORKFLOW_CHANGES.md` for implementation details

