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


async def process_message(message: str, chat_id: str, result_obj: dict, multi_mcp):
    """Process a single Telegram message through the agent"""
    # Extract message_id to track processed messages
    message_id = result_obj.get("message_id") if isinstance(result_obj, dict) else None
    
    print(f"\n📩 Received Telegram message (ID: {message_id}): {message}")
    
    # Send immediate acknowledgment to user
    if chat_id:
        try:
            acknowledgment_message = "✅ Your question has been received! Processing started...\n\nI'm working on it, please wait for the complete response."
            await multi_mcp.call_tool("send_telegram_message", {
                "input": {
                    "chat_id": chat_id,
                    "text": acknowledgment_message
                }
            })
            print(f"✅ Sent acknowledgment to Telegram (chat_id: {chat_id})")
        except Exception as e:
            print(f"⚠️ Failed to send acknowledgment: {e}")
    
    # Create agent and process
    agent = AgentLoop(
        user_input=message,
        dispatcher=multi_mcp
    )
    
    try:
        # Process the request - agent will complete all steps before returning
        final_response = await agent.run()
        
        # Extract final answer
        answer_text = ""
        if hasattr(final_response, 'final_answer'):
            answer_text = final_response.final_answer
        elif isinstance(final_response, str):
            answer_text = final_response
        else:
            answer_text = str(final_response)
        
        # Remove "FINAL_ANSWER:" prefix if present
        if answer_text.startswith("FINAL_ANSWER:"):
            answer_text = answer_text.replace("FINAL_ANSWER:", "").strip()
        
        # Extract sheet link from agent's pending sheet link or memory
        sheet_link = None
        if hasattr(agent, '_pending_sheet_link') and agent._pending_sheet_link:
            sheet_link = agent._pending_sheet_link
        else:
            # Try to extract from memory trace
            for mem in agent.context.memory_trace:
                if hasattr(mem, 'tool_name') and mem.tool_name:
                    if "get_sheet_link" in mem.tool_name.lower() or "create_google_sheet" in mem.tool_name.lower():
                        if hasattr(mem, 'text') and mem.text:
                            import re
                            # Look for Google Sheets URL in the text
                            link_match = re.search(r'https://docs\.google\.com/spreadsheets/d/[^\s"<>\'\)]+', str(mem.text))
                            if link_match:
                                sheet_link = link_match.group(0)
                                break
            
            # Also try to extract from STRUCTURED_DATA if available
            if not sheet_link:
                for mem in agent.context.memory_trace:
                    if hasattr(mem, 'text') and mem.text:
                        try:
                            import json
                            # Try to find JSON in text that might contain the link
                            json_match = re.search(r'\{[^}]*"link"[^}]*\}', str(mem.text))
                            if json_match:
                                data = json.loads(json_match.group(0))
                                if 'link' in data:
                                    sheet_link = data['link']
                                    break
                        except:
                            pass
            
            # Last resort: try to extract from final answer text
            if not sheet_link:
                link_match = re.search(r'https://docs\.google\.com/spreadsheets/d/[^\s"<>\'\)]+', answer_text)
                if link_match:
                    sheet_link = link_match.group(0)
        
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
                from modules.logger import get_logger
                logger = get_logger()
                
                import time
                start_time = time.time()
                await multi_mcp.call_tool("send_telegram_message", {
                    "input": {
                        "chat_id": chat_id,
                        "text": telegram_message
                    }
                })
                duration_ms = (time.time() - start_time) * 1000
                
                if logger:
                    logger.log_tool_call("send_telegram_message", {"chat_id": chat_id}, "sent", duration_ms)
                    logger.log_workflow_step(999, "completion", "completed", "Telegram response sent")
                    logger.log_step_completion("telegram_response", True, None)
                print(f"✅ Sent completion message to Telegram (chat_id: {chat_id})")
                if sheet_link:
                    print(f"✅ Included Google Sheet link in Telegram response")
            except Exception as e:
                print(f"⚠️ Failed to send Telegram message: {e}")
                import traceback
                traceback.print_exc()
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error processing message: {error_msg}")
        import traceback
        traceback.print_exc()
        
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
        # If so, process it immediately instead of waiting for the next loop
        if hasattr(init_response, 'content'):
            raw_text = getattr(init_response.content, 'text', None) if hasattr(init_response.content, 'text') else str(init_response.content)
            if raw_text and raw_text.strip() and not raw_text.startswith("ERROR"):
                # Try to parse the message
                import re
                import json
                
                # Check if it's a valid message response
                json_match = re.search(r'\{"message":\s*"[^"]*",\s*"chat_id":\s*"[^"]*",\s*"message_id":\s*\d+\}', str(raw_text))
                if json_match:
                    try:
                        result_obj = json.loads(json_match.group(0))
                        message = result_obj.get("message", "")
                        chat_id = result_obj.get("chat_id")
                        
                        if message and message.strip():
                            print(f"📩 Found message during initialization: {message[:50]}...")
                            # Process this message immediately
                            await process_message(message, chat_id, result_obj, multi_mcp)
                            # After processing, continue to main loop (don't skip initialization)
                            print("\n🔄 Agent is now idle, waiting for NEW messages...")
                            print("💬 Send a NEW message to your bot to start processing\n")
                    except json.JSONDecodeError:
                        pass
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
                # Use the shared process_message function
                await process_message(message, chat_id, result_obj, multi_mcp)
            
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

