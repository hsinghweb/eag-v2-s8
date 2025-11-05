"""
MCP Server for Telegram (Stdio Transport)
Provides tools to receive and send Telegram messages.
"""

from mcp.server.fastmcp import FastMCP
import sys
import os
from dotenv import load_dotenv
import requests
import time
from models import TelegramMessageOutput, TelegramSendInput

load_dotenv()

mcp = FastMCP("Telegram")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Store last update ID to avoid processing same messages
_last_update_id = 0
_message_queue = []  # Simple queue for messages
_processed_message_ids = set()  # Track processed message IDs to avoid duplicates
_processed_update_ids = set()  # Track processed update IDs to avoid duplicates

# Cleanup: Limit size of processed sets to prevent memory issues (keep last 1000)
_MAX_PROCESSED_SIZE = 1000


def mcp_log(level: str, message: str) -> None:
    sys.stderr.write(f"{level}: {message}\n")
    sys.stderr.flush()


def get_updates(offset: int = None):
    """Fetch updates from Telegram Bot API"""
    try:
        url = f"{TELEGRAM_API_URL}/getUpdates"
        params = {"timeout": 30}
        if offset:
            params["offset"] = offset
        
        response = requests.get(url, params=params, timeout=35)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        mcp_log("ERROR", f"Failed to get updates: {e}")
        return {"ok": False, "result": []}


def poll_telegram_messages():
    """Poll Telegram for new messages and queue them"""
    global _last_update_id, _processed_message_ids, _processed_update_ids
    
    if not TELEGRAM_BOT_TOKEN:
        mcp_log("ERROR", "TELEGRAM_BOT_TOKEN not set in environment")
        return
    
    updates_response = get_updates(_last_update_id + 1)
    
    if updates_response.get("ok"):
        for update in updates_response.get("result", []):
            update_id = update.get("update_id")
            
            # Skip if we've already processed this update
            if update_id in _processed_update_ids:
                mcp_log("INFO", f"Skipping already processed update_id: {update_id}")
                _last_update_id = max(_last_update_id, update_id)
                continue
            
            _last_update_id = max(_last_update_id, update_id)
            
            message = update.get("message")
            if message:
                text = message.get("text", "")
                chat_id = str(message.get("chat", {}).get("id"))
                message_id = message.get("message_id")
                
                # Skip if we've already processed this message
                if message_id in _processed_message_ids:
                    mcp_log("INFO", f"Skipping already processed message_id: {message_id}")
                    _processed_update_ids.add(update_id)
                    continue
                
                if text and text.strip():
                    # Only add if not already in queue
                    already_in_queue = any(
                        msg.get("message_id") == message_id for msg in _message_queue
                    )
                    
                    if not already_in_queue:
                        _message_queue.append({
                            "message": text,
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "update_id": update_id
                        })
                        mcp_log("INFO", f"Queued new message (ID: {message_id}): {text[:50]}...")
                    else:
                        mcp_log("INFO", f"Message ID {message_id} already in queue, skipping")
                    
                    # Mark update as processed
                    _processed_update_ids.add(update_id)


@mcp.tool()
def receive_telegram_message() -> TelegramMessageOutput:
    """
    Receive the latest message from Telegram bot.
    Polls Telegram API for new messages and returns the most recent one.
    Usage: receive_telegram_message
    """
    global _message_queue
    
    if not TELEGRAM_BOT_TOKEN:
        return TelegramMessageOutput(
            message="ERROR: TELEGRAM_BOT_TOKEN not configured",
            chat_id="",
            message_id=0
        )
    
    # Poll for new messages
    poll_telegram_messages()
    
    # Return latest message from queue, or empty if none
    if _message_queue:
        msg = _message_queue.pop(0)  # FIFO
        message_id = msg.get("message_id", 0)
        update_id = msg.get("update_id", 0)
        
        # Mark message as processed to avoid reprocessing
        if message_id:
            _processed_message_ids.add(message_id)
        if update_id:
            _processed_update_ids.add(update_id)
        
        # Cleanup old processed IDs to prevent memory issues (keep sets manageable)
        if len(_processed_message_ids) > _MAX_PROCESSED_SIZE:
            # Remove half of the entries (sets are unordered, so we remove arbitrary ones)
            to_remove = list(_processed_message_ids)[:_MAX_PROCESSED_SIZE//2]
            for msg_id in to_remove:
                _processed_message_ids.discard(msg_id)
            mcp_log("INFO", f"Cleaned up {len(to_remove)} old processed message IDs. Remaining: {len(_processed_message_ids)}")
        
        if len(_processed_update_ids) > _MAX_PROCESSED_SIZE:
            # Remove half of the entries
            to_remove = list(_processed_update_ids)[:_MAX_PROCESSED_SIZE//2]
            for upd_id in to_remove:
                _processed_update_ids.discard(upd_id)
            mcp_log("INFO", f"Cleaned up {len(to_remove)} old processed update IDs. Remaining: {len(_processed_update_ids)}")
        
        mcp_log("INFO", f"Returning message (ID: {message_id}, Update: {update_id}): {msg['message'][:50]}...")
        mcp_log("INFO", f"Marked message_id {message_id} as processed. Queue size: {len(_message_queue)}, Processed: {len(_processed_message_ids)}")
        
        return TelegramMessageOutput(
            message=msg["message"],
            chat_id=msg["chat_id"],
            message_id=message_id
        )
    else:
        return TelegramMessageOutput(
            message="",
            chat_id="",
            message_id=0
        )


@mcp.tool()
def send_telegram_message(input: TelegramSendInput) -> str:
    """
    Send a message via Telegram bot.
    Usage: send_telegram_message|input.chat_id="123456789"|input.text="Hello!"
    """
    if not TELEGRAM_BOT_TOKEN:
        return "ERROR: TELEGRAM_BOT_TOKEN not configured"
    
    try:
        url = f"{TELEGRAM_API_URL}/sendMessage"
        payload = {
            "chat_id": input.chat_id,
            "text": input.text
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("ok"):
            mcp_log("INFO", f"Message sent to {input.chat_id}")
            return f"Message sent successfully. Message ID: {result.get('result', {}).get('message_id', 'unknown')}"
        else:
            return f"Failed to send message: {result.get('description', 'Unknown error')}"
    except Exception as e:
        mcp_log("ERROR", f"Error sending message: {e}")
        return f"ERROR: {str(e)}"


@mcp.tool()
def poll_telegram_once() -> str:
    """
    Poll Telegram API once for new messages (for testing).
    Usage: poll_telegram_once
    """
    if not TELEGRAM_BOT_TOKEN:
        return "ERROR: TELEGRAM_BOT_TOKEN not configured"
    
    poll_telegram_messages()
    queue_size = len(_message_queue)
    return f"Polled Telegram. Queue size: {queue_size}"


if __name__ == "__main__":
    print("mcp_server_telegram.py starting")
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        mcp.run()  # Run without transport for dev server
    else:
        mcp.run(transport="stdio")
        print("\nShutting down...")

