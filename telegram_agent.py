"""
Telegram-enabled Agent
Polls Telegram for messages and processes them through the agent loop.
"""

import asyncio
import yaml
import time
from core.loop import AgentLoop
from core.session import MultiMCP

def log(stage: str, msg: str):
    """Simple timestamped console logger."""
    import datetime
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{stage}] {msg}")


async def poll_and_process():
    """Poll Telegram for messages and process them"""
    print("🧠 Cortex-R Telegram Agent Ready")
    print("📱 Polling Telegram for messages...")
    print("💬 Send a message to your bot to start processing")
    
    # Load MCP server configs from profiles.yaml
    with open("config/profiles.yaml", "r") as f:
        profile = yaml.safe_load(f)
        mcp_servers = profile.get("mcp_servers", [])
    
    multi_mcp = MultiMCP(server_configs=mcp_servers)
    print("Agent before initialize")
    await multi_mcp.initialize()
    
    # Initialize Telegram offset to skip old messages
    print("📱 Initializing Telegram - skipping old messages...")
    try:
        # Call a tool to initialize offset (this will be handled by the server)
        await multi_mcp.call_tool("receive_telegram_message", {})
        print("✅ Telegram initialized. Agent will only process NEW messages sent after this point.")
    except Exception as e:
        print(f"⚠️ Telegram initialization note: {e}")
    
    print("\n🔄 Agent is now idle, waiting for NEW messages...")
    print("💬 Send a NEW message to your bot to start processing\n")
    
    while True:
        try:
            # Check for Telegram message
            from modules.action import parse_function_call
            
            # Use the Telegram tool to receive message
            response = await multi_mcp.call_tool("receive_telegram_message", {})
            
            # Parse response - handle TextContent objects
            raw_text = getattr(response.content, 'text', None)
            if raw_text is None:
                raw_text = str(response.content)
            
            # Initialize variables
            message = ""
            chat_id = None
            result_obj = {}
            
            # Clean up if it's a string representation of TextContent or contains TextContent
            if "TextContent" in str(raw_text):
                import re
                import json
                # Extract JSON content from TextContent string representation
                # Look for full JSON object
                json_match = re.search(r'\{"message":\s*"[^"]*",\s*"chat_id":\s*"[^"]*",\s*"message_id":\s*\d+\}', str(raw_text))
                if json_match:
                    try:
                        result_obj = json.loads(json_match.group(0))
                        message = result_obj.get("message", "")
                        chat_id = result_obj.get("chat_id")
                    except json.JSONDecodeError:
                        # Fallback: extract message only
                        msg_match = re.search(r'"message":\s*"([^"]*)"', str(raw_text))
                        if msg_match:
                            message = msg_match.group(1)
                        chat_match = re.search(r'"chat_id":\s*"([^"]*)"', str(raw_text))
                        if chat_match:
                            chat_id = chat_match.group(1)
                else:
                    # Try to extract message and chat_id separately
                    msg_match = re.search(r'"message":\s*"([^"]*)"', str(raw_text))
                    if msg_match:
                        message = msg_match.group(1)
                    chat_match = re.search(r'"chat_id":\s*"([^"]*)"', str(raw_text))
                    if chat_match:
                        chat_id = chat_match.group(1)
            else:
                # Try parsing as JSON
                try:
                    import json
                    if raw_text.strip().startswith("{"):
                        result_obj = json.loads(raw_text)
                        message = result_obj.get("message", "") if isinstance(result_obj, dict) else ""
                        chat_id = result_obj.get("chat_id") if isinstance(result_obj, dict) else None
                    else:
                        message = raw_text.strip()
                except json.JSONDecodeError:
                    message = raw_text.strip() if raw_text else ""
            
            if message and message.strip() and not message.startswith("ERROR"):
                # Extract message_id to track processed messages
                message_id = result_obj.get("message_id") if isinstance(result_obj, dict) else None
                
                print(f"\n📩 Received Telegram message (ID: {message_id}): {message}")
                
                # Create agent and process
                agent = AgentLoop(
                    user_input=message,
                    dispatcher=multi_mcp
                )
                
                try:
                    # Process the request WITHOUT sending progress messages (no ping-pong)
                    final_response = await agent.run()
                    answer_text = final_response.replace("FINAL_ANSWER:", "").strip()
                    print("\n💡 Final Answer:\n", answer_text)
                    
                    # Send ONLY final response back to Telegram when task completes
                    if chat_id:
                        try:
                            await multi_mcp.call_tool("send_telegram_message", {
                                "input": {
                                    "chat_id": chat_id,
                                    "text": f"✅ Task Completed!\n\n{answer_text}"
                                }
                            })
                            print(f"✅ Sent completion message to Telegram (chat_id: {chat_id})")
                        except Exception as e:
                            log("error", f"Failed to send Telegram response: {e}")
                
                except Exception as e:
                    error_msg = f"Agent encountered an error: {str(e)[:200]}"
                    print(f"\n❌ {error_msg}")
                    log("fatal", f"Agent failed: {e}")
                    
                    # Send error message to Telegram
                    if chat_id:
                        try:
                            await multi_mcp.call_tool("send_telegram_message", {
                                "input": {
                                    "chat_id": chat_id,
                                    "text": f"❌ Error occurred: {error_msg}"
                                }
                            })
                        except:
                            pass
                
                # Mark message as processed (already done in mcp_server_telegram, but log it)
                if message_id:
                    print(f"✅ Message (ID: {message_id}) processed and marked as complete. Will not process again.")
            
            # Poll interval - check every 5 seconds for new messages
            await asyncio.sleep(5)  # Check every 5 seconds
            
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
            break
        except Exception as e:
            log("error", f"Polling error: {e}")
            await asyncio.sleep(10)  # Wait longer on error


if __name__ == "__main__":
    asyncio.run(poll_and_process())

