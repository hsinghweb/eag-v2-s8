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
    
    while True:
        try:
            # Check for Telegram message
            from modules.action import parse_function_call
            
            # Use the Telegram tool to receive message
            response = await multi_mcp.call_tool("receive_telegram_message", {})
            
            # Parse response
            raw = getattr(response.content, 'text', str(response.content))
            try:
                import json
                result_obj = json.loads(raw) if raw.strip().startswith("{") else raw
            except json.JSONDecodeError:
                result_obj = raw
            
            # Extract message
            if isinstance(result_obj, dict):
                message = result_obj.get("message", "")
            else:
                # Try to parse as string
                try:
                    import json
                    parsed = json.loads(raw)
                    message = parsed.get("message", "")
                except:
                    message = str(result_obj)
            
            if message and message.strip() and not message.startswith("ERROR"):
                print(f"\n📩 Received Telegram message: {message}")
                
                # Create agent and process
                agent = AgentLoop(
                    user_input=message,
                    dispatcher=multi_mcp
                )
                
                try:
                    final_response = await agent.run()
                    print("\n💡 Final Answer:\n", final_response.replace("FINAL_ANSWER:", "").strip())
                    
                    # Optionally send response back to Telegram
                    chat_id = result_obj.get("chat_id") if isinstance(result_obj, dict) else None
                    if chat_id:
                        try:
                            await multi_mcp.call_tool("send_telegram_message", {
                                "input": {
                                    "chat_id": chat_id,
                                    "text": f"✅ Completed!\n\n{final_response.replace('FINAL_ANSWER:', '').strip()}"
                                }
                            })
                        except Exception as e:
                            log("error", f"Failed to send Telegram response: {e}")
                
                except Exception as e:
                    log("fatal", f"Agent failed: {e}")
            
            # Poll interval
            await asyncio.sleep(5)  # Check every 5 seconds
            
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
            break
        except Exception as e:
            log("error", f"Polling error: {e}")
            await asyncio.sleep(10)  # Wait longer on error


if __name__ == "__main__":
    asyncio.run(poll_and_process())

