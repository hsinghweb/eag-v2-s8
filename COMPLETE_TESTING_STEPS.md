# Complete Step-by-Step Testing Guide

Follow these steps in order. Don't skip ahead!

---

## STEP 1: Install Python Dependencies ✅

You've already done this! But just to confirm:

```bash
python -m pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-telegram-bot fastapi uvicorn python-dotenv pydantic-settings
```

---

## STEP 2: Install Ollama Models

Open a terminal and run:

```bash
# Required models
ollama pull nomic-embed-text
ollama pull phi3:mini

# Optional - for image captioning
ollama pull gemma2:2b
```

Wait for all models to download. This may take a few minutes.

**Verify installation:**
```bash
ollama list
```
You should see the models listed.

---

## STEP 3: Set Up Telegram Bot

1. Open Telegram app (on phone or desktop)
2. Search for **@BotFather**
3. Send `/newbot` command
4. Follow the prompts:
   - Choose a name for your bot (e.g., "My F1 Agent")
   - Choose a username (e.g., "my_f1_agent_bot")
5. **Copy the bot token** (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

6. Create a file named `.env` in the project folder (`d:\Himanshu\EAG-V2\eag-v2-s8\.env`)

7. Add this line to `.env`:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

Replace `your_bot_token_here` with the actual token you copied.

**Test your bot:**
- Open Telegram
- Search for your bot by username
- Send a message like "Hello"
- The bot should receive it (you'll see it later when testing)

---

## STEP 4: Set Up Google APIs

### 4.1 Create Google Cloud Project

1. Go to https://console.cloud.google.com/
2. Click "Select a project" → "New Project"
3. Give it a name (e.g., "EAG Agent")
4. Click "Create"

### 4.2 Enable APIs

1. In Google Cloud Console, go to **APIs & Services** → **Library**
2. Search and enable each of these:
   - **Gmail API** → Click "Enable"
   - **Google Sheets API** → Click "Enable"
   - **Google Drive API** → Click "Enable"

### 4.3 Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **"Create Credentials"** → **"OAuth client ID"**
3. If asked, configure OAuth consent screen:
   - User Type: **External**
   - App name: "EAG Agent" (or any name)
   - User support email: Your email
   - Developer contact: Your email
   - Click **Save and Continue**
   - Scopes: Click **Save and Continue** (no need to add scopes here)
   - Test users: **ADD YOURSELF** (your email address)
   - Click **Save and Continue**

4. Now create OAuth client ID:
   - Application type: **Desktop app**
   - Name: "EAG Agent Desktop"
   - Click **Create**

5. **Download the JSON file** (a download should start automatically)
   - Save it as `credentials.json` in your project folder
   - **Rename it to `gmail_credentials.json`**
   - **Copy it again and name it `credentials.json`** (you need both files)

Your project folder should now have:
- `credentials.json` (for Google Sheets/Drive)
- `gmail_credentials.json` (for Gmail)

### 4.4 Generate OAuth Tokens

Open terminal in your project folder and run:

```bash
python setup_google_oauth.py
```

**What happens:**
1. A browser window will open
2. Sign in with your Google account
3. You'll see a warning "This app isn't verified" - Click **"Advanced"** → **"Go to [Your App Name] (unsafe)"**
4. Click **"Allow"** to grant permissions
5. Browser will show "localhost refused to connect" - **This is normal!**
6. Terminal will show: `✅ Gmail token saved to gmail_token.json`
7. Browser opens again for Sheets/Drive permissions - repeat steps 3-5
8. Terminal will show: `✅ Google Sheets/Drive token saved to token.json`

**Verify files created:**
Check that these files exist in your project folder:
- ✅ `gmail_token.json`
- ✅ `token.json`

---

## STEP 5: Start Google Sheets/Drive Server (SSE)

**Open Terminal 1:**

```bash
cd d:\Himanshu\EAG-V2\eag-v2-s8
python mcp_server_gdrive.py
```

**You should see:**
```
🚀 Starting Google Sheets/Drive MCP Server (SSE) on port 8002
📋 MCP endpoint: http://localhost:8002/mcp/tools
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8002
```

**✅ Keep this terminal running! Don't close it!**

**Test it's working:**
Open another terminal and run:
```bash
curl http://localhost:8002/mcp/tools
```
You should see JSON with tool definitions.

---

## STEP 6: Start Telegram Agent

**Open Terminal 2** (new terminal window):

```bash
cd d:\Himanshu\EAG-V2\eag-v2-s8
python telegram_agent.py
```

**You should see:**
```
🧠 Cortex-R Telegram Agent Ready
📱 Polling Telegram for messages...
💬 Send a message to your bot to start processing
in MultiMCP initialize
→ Scanning tools from: mcp_server_1.py in ...
→ Scanning tools from: mcp_server_2.py in ...
→ Scanning tools from: mcp_server_3.py in ...
→ Scanning tools from: mcp_server_telegram.py in ...
→ Scanning tools from: mcp_server_gmail.py in ...
→ Scanning SSE tools from: http://localhost:8002
```

**✅ Keep this terminal running too!**

---

## STEP 7: Send Test Message via Telegram

1. Open **Telegram app** (on phone or desktop)
2. Find your bot (search for the username you created)
3. **Start a conversation** with the bot
4. Send this exact message:
   ```
   Find the Current Point Standings of F1 Racers
   ```

---

## STEP 8: Watch the Agent Work!

**In Terminal 2** (where `telegram_agent.py` is running), you should see:

```
📩 Received Telegram message: Find the Current Point Standings of F1 Racers
[perception] Intent: search_f1_standings
[plan] FUNCTION_CALL: search|query="F1 current point standings 2024"
[action] search → [search results]
[plan] FUNCTION_CALL: create_google_sheet|input.title="F1 Standings"
[action] create_google_sheet → sheet_id: abc123...
[plan] FUNCTION_CALL: add_data_to_sheet|input.sheet_id=abc123|input.data=[[...]]
[action] add_data_to_sheet → success
[plan] FUNCTION_CALL: get_sheet_link|input.sheet_id=abc123
[action] get_sheet_link → https://docs.google.com/spreadsheets/d/...
[plan] FUNCTION_CALL: send_email_with_link|to=your_email|sheet_link=...
[action] send_email_with_link → success
💡 Final Answer: [F1 standings sheet created and emailed]
```

---

## STEP 9: Verify Results

### 9.1 Check Google Drive

1. Go to https://drive.google.com/
2. Look for a new file named **"F1 Standings"**
3. Open it - you should see F1 driver standings data

### 9.2 Check Gmail

1. Go to https://gmail.com/
2. Check your inbox
3. Look for an email with subject about F1 Standings
4. The email should contain a link to the Google Sheet
5. Click the link - it should open the sheet

### 9.3 Check Telegram

The agent may also send a response back to Telegram showing completion.

---

## ✅ Success Checklist

- [ ] Ollama models installed
- [ ] Telegram bot created and token in `.env`
- [ ] Google APIs enabled
- [ ] OAuth credentials downloaded
- [ ] OAuth tokens generated (`gmail_token.json`, `token.json`)
- [ ] Google Sheets/Drive server running (Terminal 1)
- [ ] Telegram agent running (Terminal 2)
- [ ] Test message sent via Telegram
- [ ] Agent processed the message
- [ ] Google Sheet created in Drive
- [ ] Email received with sheet link
- [ ] Sheet link works and shows F1 data

---

## 🐛 Troubleshooting

### "Tool not found" error
- Make sure Terminal 1 (SSE server) is still running
- Check `http://localhost:8002` is accessible

### "TELEGRAM_BOT_TOKEN not configured"
- Check `.env` file exists and has the token
- Make sure token is correct (no extra spaces)

### "Google API error"
- Re-run: `python setup_google_oauth.py`
- Check `gmail_token.json` and `token.json` exist

### "Connection refused" on SSE server
- Make sure `mcp_server_gdrive.py` is running
- Check port 8002 is not blocked

### Agent not receiving Telegram messages
- Make sure you started a conversation with the bot first
- Check bot token is correct
- Wait a few seconds and send message again

---

## 🎯 Summary

**What you need running:**
1. ✅ Terminal 1: `python mcp_server_gdrive.py` (SSE server)
2. ✅ Terminal 2: `python telegram_agent.py` (agent)

**What happens:**
1. Send message on Telegram
2. Agent receives it
3. Agent searches for F1 standings
4. Agent creates Google Sheet with data
5. Agent sends email with sheet link
6. You receive email with link!

**Total time:** ~5-10 minutes for setup, then instant results!

---

## 📞 Quick Reference

**Files you should have:**
- `.env` (with TELEGRAM_BOT_TOKEN)
- `credentials.json` (Google Sheets/Drive)
- `gmail_credentials.json` (Gmail)
- `token.json` (generated by setup script)
- `gmail_token.json` (generated by setup script)

**Commands to remember:**
```bash
# Terminal 1:
python mcp_server_gdrive.py

# Terminal 2:
python telegram_agent.py
```

---

**You're all set! Follow these steps and you'll have it working!** 🚀

