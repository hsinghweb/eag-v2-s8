# Quick Testing Guide

## 🚀 Quick Start

### 1. Install Dependencies
```bash
uv sync
```

### 2. Set Up Credentials

#### Telegram
1. Create bot via @BotFather on Telegram
2. Get bot token
3. Add to `.env`:
```env
TELEGRAM_BOT_TOKEN=your_token_here
```

#### Google APIs
1. Download OAuth2 credentials from Google Cloud Console
2. Save as:
   - `gmail_credentials.json` (for Gmail)
   - `credentials.json` (for Sheets/Drive)
3. Run OAuth setup:
```bash
python setup_google_oauth.py
```

### 3. Start Google Sheets/Drive SSE Server

**Terminal 1:**
```bash
python mcp_server_gdrive.py
```
Keep this running!

### 4. Start Telegram Agent

**Terminal 2:**
```bash
python telegram_agent.py
```

### 5. Send Test Message

1. Open Telegram app
2. Find your bot
3. Send: **"Find the Current Point Standings of F1 Racers"**

### 6. Watch the Magic! ✨

The agent will:
- ✅ Receive your Telegram message
- ✅ Search for F1 standings
- ✅ Create Google Sheet
- ✅ Add data to sheet
- ✅ Send email with sheet link

---

## 📋 Testing Checklist

### Before Testing
- [ ] Ollama running on `http://localhost:11434`
- [ ] Required models installed: `nomic-embed-text`, `phi3:mini` (and optionally `gemma2:2b` for vision)
- [ ] Telegram bot created and token in `.env`
- [ ] Google credentials files downloaded
- [ ] OAuth tokens generated (`gmail_token.json`, `token.json`)
- [ ] `.env` file configured

### During Testing
- [ ] SSE server (mcp_server_gdrive.py) running on port 8002
- [ ] Telegram agent (telegram_agent.py) running and polling
- [ ] Message sent to Telegram bot
- [ ] Agent receives message
- [ ] Google Sheet created (check Google Drive)
- [ ] Email received in Gmail

---

## 🔧 Troubleshooting

### "Tool not found" error
- Check `config/profiles.yaml` has all servers configured
- Verify SSE server is running
- Restart agent

### Telegram not receiving messages
- Verify bot token is correct
- Make sure you've started conversation with bot first
- Check Telegram API is accessible

### Google API errors
- Re-run `python setup_google_oauth.py` if tokens expired
- Verify credentials files exist
- Check APIs are enabled in Google Cloud Console

### SSE server connection failed
- Verify server is running: `curl http://localhost:8002/mcp/tools`
- Check port 8002 is not blocked
- Restart SSE server

---

## 📝 Example Workflow

1. **Start SSE server**:
   ```bash
   python mcp_server_gdrive.py
   ```

2. **Start Telegram agent**:
   ```bash
   python telegram_agent.py
   ```

3. **Send Telegram message**:
   - Open Telegram
   - Send: "Find the Current Point Standings of F1 Racers"

4. **Expected agent actions**:
   ```
   📩 Received Telegram message: Find the Current Point Standings of F1 Racers
   [perception] Intent: search_f1_standings
   [plan] FUNCTION_CALL: search|query="F1 current point standings 2024"
   [action] search → [results]
   [plan] FUNCTION_CALL: create_google_sheet|input.title="F1 Standings"
   [action] create_google_sheet → sheet_id: ...
   [plan] FUNCTION_CALL: add_data_to_sheet|input.sheet_id=...|input.data=[[...]]
   [action] add_data_to_sheet → success
   [plan] FUNCTION_CALL: get_sheet_link|input.sheet_id=...
   [action] get_sheet_link → https://docs.google.com/spreadsheets/d/...
   [plan] FUNCTION_CALL: send_email_with_link|to=...|sheet_link=...
   [action] send_email_with_link → success
   💡 Final Answer: [F1 standings sheet created and emailed]
   ```

5. **Verify**:
   - Check Google Drive for new sheet
   - Check Gmail for email with link
   - Open link and verify data is present

---

## 🎯 Alternative: Manual Testing (Without Telegram)

If you want to test without Telegram first:

```bash
python agent.py
# Then manually enter: "Find the Current Point Standings of F1 Racers"
```

This bypasses Telegram and lets you test the workflow directly.

---

## 📚 Full Documentation

See `SETUP_AND_TESTING.md` for detailed setup instructions.

