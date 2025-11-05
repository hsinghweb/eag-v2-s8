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
        # This first call will initialize the offset and acknowledge old messages
        init_response = await multi_mcp.call_tool("receive_telegram_message", {})
        print("✅ Telegram initialized. Agent will only process NEW messages sent after this point.")
        
        # Check if there's already a message queued from initialization
        # Parse the response to see if we got a message
        if hasattr(init_response, 'content'):
            raw_text = getattr(init_response.content, 'text', None) if hasattr(init_response.content, 'text') else str(init_response.content)
            if raw_text and raw_text.strip() and not raw_text.startswith("ERROR") and '"message"' in str(raw_text):
                print("⚠️ Note: Found a message during initialization - it will be processed in the next loop iteration")
    except Exception as e:
        print(f"⚠️ Telegram initialization note: {e}")
    
    print("\n🔄 Agent is now idle, waiting for NEW messages...")
    print("💬 Send a NEW message to your bot to start processing\n")
    
    while True:
        try:
            # Check for Telegram message
            from modules.action import parse_function_call
            
            # Use the Telegram tool to receive message
            # First call might initialize offset, so we always call it to ensure polling happens
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
                    
                    # Extract sheet link from agent's memory to include in Telegram response
                    sheet_link = None
                    try:
                        import re
                        import json
                        
                        # Priority 1: Try to get from agent's pending sheet link (most reliable)
                        if hasattr(agent, '_pending_sheet_link') and agent._pending_sheet_link:
                            sheet_link = agent._pending_sheet_link
                            print(f"✅ Found sheet link from _pending_sheet_link: {sheet_link[:80]}...")
                        
                        # Priority 2: Search in memory trace for get_sheet_link results (check STRUCTURED_DATA)
                        if not sheet_link:
                            for mem in agent.context.memory_trace:
                                if hasattr(mem, 'tool_name') and mem.tool_name and "get_sheet_link" in mem.tool_name.lower():
                                    if hasattr(mem, 'text') and mem.text:
                                        # Try to parse STRUCTURED_DATA JSON first
                                        if 'STRUCTURED_DATA' in str(mem.text):
                                            try:
                                                # Extract JSON from STRUCTURED_DATA
                                                json_match = re.search(r'\[STRUCTURED_DATA\]:\s*(\{.*?\})', str(mem.text), re.DOTALL)
                                                if json_match:
                                                    data = json.loads(json_match.group(1))
                                                    if isinstance(data, dict):
                                                        sheet_link = data.get("link") or data.get("sheet_url") or data.get("sheetUrl")
                                                        if sheet_link:
                                                            print(f"✅ Found sheet link from STRUCTURED_DATA: {sheet_link[:80]}...")
                                                            break
                                            except json.JSONDecodeError:
                                                pass
                                        
                                        # Fallback: regex extraction from text
                                        if not sheet_link:
                                            # Match full URL including query parameters (e.g., ?gid=0#gid=0)
                                            # Pattern matches: https://docs.google.com/spreadsheets/d/SHEET_ID/edit?gid=0#gid=0
                                            link_match = re.search(r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9_-]+(/edit)?(\?[^\s"<>)]*)?(#[^\s"<>)]*)?', str(mem.text))
                                            if link_match:
                                                sheet_link = link_match.group(0)
                                                print(f"✅ Found sheet link from memory text: {sheet_link[:80]}...")
                                                break
                        
                        # Priority 3: Try to extract from create_google_sheet result (sheet_url)
                        if not sheet_link:
                            for mem in agent.context.memory_trace:
                                if hasattr(mem, 'tool_name') and mem.tool_name and "create_google_sheet" in mem.tool_name.lower():
                                    if hasattr(mem, 'text') and mem.text:
                                        if 'STRUCTURED_DATA' in str(mem.text):
                                            try:
                                                json_match = re.search(r'\[STRUCTURED_DATA\]:\s*(\{.*?\})', str(mem.text), re.DOTALL)
                                                if json_match:
                                                    data = json.loads(json_match.group(1))
                                                    if isinstance(data, dict):
                                                        sheet_link = data.get("sheet_url") or data.get("sheetUrl")
                                                        if sheet_link:
                                                            print(f"✅ Found sheet link from create_google_sheet: {sheet_link[:80]}...")
                                                            break
                                            except json.JSONDecodeError:
                                                pass
                        
                        # Priority 4: Extract from final answer text
                        if not sheet_link:
                            # Match full URL including query parameters (e.g., ?gid=0#gid=0)
                            link_match = re.search(r'https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9_-]+(/edit)?(\?[^\s"<>)]*)?(#[^\s"<>)]*)?', answer_text)
                            if link_match:
                                sheet_link = link_match.group(0)
                                print(f"✅ Found sheet link from final answer: {sheet_link[:80]}...")
                        
                        if not sheet_link:
                            print("⚠️ Could not extract sheet link from any source")
                    except Exception as e:
                        log("error", f"Failed to extract sheet link: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    # Build enhanced Telegram message with sheet link
                    if sheet_link:
                        # Clean up the link (remove any trailing characters that might break it)
                        sheet_link = sheet_link.strip().rstrip('.,;:!?')
                        
                        # Create a nicely formatted response
                        telegram_message = f"""✅ Task Completed Successfully!

📊 Your data has been organized in a Google Sheet.

🔗 Open the Sheet:
{sheet_link}

💡 You can view, edit, and share this sheet directly from the link above."""
                    else:
                        # Fallback if link not found
                        telegram_message = f"""✅ Task Completed!

{answer_text}

⚠️ Note: Google Sheet was created but the link could not be retrieved automatically."""
                    
                    # Send ONLY final response back to Telegram when task completes
                    if chat_id:
                        try:
                            await multi_mcp.call_tool("send_telegram_message", {
                                "input": {
                                    "chat_id": chat_id,
                                    "text": telegram_message
                                }
                            })
                            print(f"✅ Sent completion message to Telegram (chat_id: {chat_id})")
                            if sheet_link:
                                print(f"✅ Included Google Sheet link in Telegram response")
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
            
            # Poll interval - no sleep needed since getUpdates uses long polling (timeout=30)
            # This means Telegram will wait up to 30 seconds for new messages, so we don't need to sleep
            # The getUpdates call itself will block until a message arrives or timeout
            # For faster response, we can use a short sleep if no message was found
            if not message or not message.strip():
                await asyncio.sleep(2)  # Short sleep only if no message found
            
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
            break
        except Exception as e:
            log("error", f"Polling error: {e}")
            await asyncio.sleep(10)  # Wait longer on error


if __name__ == "__main__":
    asyncio.run(poll_and_process())

