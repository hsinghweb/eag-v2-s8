# core/loop.py

import asyncio
from core.context import AgentContext
from core.session import MultiMCP
from core.strategy import decide_next_action
from modules.perception import extract_perception, PerceptionResult
from modules.action import ToolCallResult, parse_function_call
from modules.memory import MemoryItem
import json


class AgentLoop:
    def __init__(self, user_input: str, dispatcher: MultiMCP):
        self.context = AgentContext(user_input)
        self.mcp = dispatcher
        self.tools = dispatcher.get_all_tools()

    def tool_expects_input(self, tool_name: str) -> bool:
        tool = next((t for t in self.tools if getattr(t, "name", None) == tool_name), None)
        if not tool:
            return False
        parameters = getattr(tool, "parameters", {})
        return list(parameters.keys()) == ["input"]

    

    async def run(self) -> str:
        print(f"[agent] Starting session: {self.context.session_id}")

        try:
            max_steps = self.context.agent_profile.max_steps
            query = self.context.user_input
            consecutive_failures = 0
            max_failures = 2  # Allow 2 consecutive failures before giving up

            for step in range(max_steps):
                self.context.step = step
                print(f"[loop] Step {step + 1} of {max_steps}")

                # 🧠 Perception
                perception_raw = await extract_perception(query)


                # ✅ Exit cleanly on FINAL_ANSWER
                # ✅ Handle string outputs safely before trying to parse
                if isinstance(perception_raw, str):
                    pr_str = perception_raw.strip()
                    
                    # Clean exit if it's a FINAL_ANSWER
                    if pr_str.startswith("FINAL_ANSWER:"):
                        self.context.final_answer = pr_str
                        break

                    # Detect LLM echoing the prompt
                    if "Your last tool produced this result" in pr_str or "Original user task:" in pr_str:
                        print("[perception] ⚠️ LLM likely echoed prompt. No actionable plan.")
                        self.context.final_answer = "FINAL_ANSWER: [no result]"
                        break

                    # Try to decode stringified JSON if it looks valid
                    try:
                        perception_raw = json.loads(pr_str)
                    except json.JSONDecodeError:
                        print("[perception] ⚠️ LLM response was neither valid JSON nor actionable text.")
                        self.context.final_answer = "FINAL_ANSWER: [no result]"
                        break


                # ✅ Try parsing PerceptionResult
                if isinstance(perception_raw, PerceptionResult):
                    perception = perception_raw
                else:
                    try:
                        # Attempt to parse stringified JSON if needed
                        if isinstance(perception_raw, str):
                            perception_raw = json.loads(perception_raw)
                        perception = PerceptionResult(**perception_raw)
                    except Exception as e:
                        print(f"[perception] ⚠️ LLM perception failed: {e}")
                        print(f"[perception] Raw output: {perception_raw}")
                        # Create fallback perception with basic info from user input
                        perception = PerceptionResult(
                            user_input=query,
                            intent="process query",
                            entities=[],
                            tool_hint="search" if any(word in query.lower() for word in ["find", "search", "get", "show"]) else None
                        )
                        print(f"[perception] Using fallback perception: {perception.intent}, {perception.tool_hint}")

                # Validate perception before proceeding
                if not hasattr(perception, 'user_input') or not perception.user_input:
                    perception.user_input = query
                
                print(f"[perception] Intent: {perception.intent or 'None'}, Hint: {perception.tool_hint or 'None'}")

                # 💾 Memory Retrieval
                retrieved = self.context.memory.retrieve(
                    query=query,
                    top_k=self.context.agent_profile.memory_config["top_k"],
                    type_filter=self.context.agent_profile.memory_config.get("type_filter", None),
                    session_filter=self.context.session_id
                )
                print(f"[memory] Retrieved {len(retrieved)} memories")

                # 📊 Planning (via strategy)
                plan = await decide_next_action(
                    context=self.context,
                    perception=perception,
                    memory_items=retrieved,
                    all_tools=self.tools
                )
                print(f"[plan] {plan}")

                if "FINAL_ANSWER:" in plan:
                    # Optionally extract the final answer portion
                    final_lines = [line for line in plan.splitlines() if line.strip().startswith("FINAL_ANSWER:")]
                    if final_lines:
                        self.context.final_answer = final_lines[-1].strip()
                    else:
                        self.context.final_answer = "FINAL_ANSWER: [result found, but could not extract]"
                    break


                # ⚙️ Tool Execution
                try:
                    tool_name, arguments = parse_function_call(plan)

                    if self.tool_expects_input(tool_name):
                        tool_input = {'input': arguments} if not (isinstance(arguments, dict) and 'input' in arguments) else arguments
                    else:
                        tool_input = arguments

                    response = await self.mcp.call_tool(tool_name, tool_input)

                    # ✅ Safe TextContent parsing
                    raw = getattr(response.content, 'text', str(response.content))
                    try:
                        result_obj = json.loads(raw) if raw.strip().startswith("{") else raw
                    except json.JSONDecodeError:
                        result_obj = raw

                    result_str = result_obj.get("markdown") if isinstance(result_obj, dict) else str(result_obj)
                    print(f"[action] {tool_name} → {result_str}")

                    # 🧠 Add memory
                    memory_item = MemoryItem(
                        text=f"{tool_name}({arguments}) → {result_str}",
                        type="tool_output",
                        tool_name=tool_name,
                        user_query=query,
                        tags=[tool_name],
                        session_id=self.context.session_id
                    )
                    self.context.add_memory(memory_item)

                    # Reset failure counter on success
                    consecutive_failures = 0
                    
                    # 🔁 Next query
                    query = f"""Original user task: {self.context.user_input}

    Your last tool produced this result:

    {result_str}

    If this fully answers the task, return:
    FINAL_ANSWER: your answer

    Otherwise, return the next FUNCTION_CALL."""
                except Exception as e:
                    print(f"[error] Tool execution failed: {e}")
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        print(f"[agent] Too many failures ({consecutive_failures}). Stopping.")
                        self.context.final_answer = "FINAL_ANSWER: [Agent encountered errors and stopped]"
                        break
                    # Try to continue with next step
                    query = f"""Original user task: {self.context.user_input}
                    
Error occurred in previous step: {e}

Try a different approach or provide FINAL_ANSWER if task cannot be completed."""
                    continue

        except Exception as e:
            print(f"[agent] Session failed: {e}")

        return self.context.final_answer or "FINAL_ANSWER: [no result]"


