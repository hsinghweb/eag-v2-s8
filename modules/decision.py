from typing import List, Optional
from modules.perception import PerceptionResult
from modules.memory import MemoryItem
from modules.model_manager import ModelManager
from dotenv import load_dotenv
from google import genai
import os
import asyncio

# Optional: import logger if available
try:
    from agent import log
except ImportError:
    import datetime
    def log(stage: str, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{stage}] {msg}")

model = ModelManager()


async def generate_plan(
    perception: PerceptionResult,
    memory_items: List[MemoryItem],
    tool_descriptions: Optional[str] = None,
    step_num: int = 1,
    max_steps: int = 3
) -> str:
    """Generates the next step plan for the agent: either tool usage or final answer."""

    memory_texts = "\n".join(f"- {m.text}" for m in memory_items) or "None"
    tool_context = f"\nYou have access to the following tools:\n{tool_descriptions}" if tool_descriptions else ""

    # Check what tools have been used
    used_tools = []
    for m in memory_items:
        if hasattr(m, 'tool_name') and m.tool_name:
            used_tools.append(m.tool_name)
    used_tools_text = ", ".join(set(used_tools)) if used_tools else "None yet"
    
    # Determine if we're near the end
    remaining_steps = max_steps - step_num + 1
    is_last_step = remaining_steps <= 2
    
    prompt = f"""
You are a reasoning-driven AI agent with access to tools and memory.
Your job is to solve the user's request step-by-step by reasoning through the problem, selecting a tool if needed, and continuing until the FINAL_ANSWER is produced.

Respond in **exactly one line** using one of the following formats:

- FUNCTION_CALL: tool_name|param1=value1|param2=value2
- FINAL_ANSWER: [your final result] *(Not description, but actual final answer)

🧠 Context:
- Step: {step_num} of {max_steps} ({remaining_steps} steps remaining)
- {'⚠️ LAST FEW STEPS - Must complete task soon!' if is_last_step else ''}
- Tools already used: {used_tools_text}
- Memory from previous steps: 
{memory_texts}
{tool_context}

🎯 User Request: "{perception.user_input}"
- Intent: {perception.intent or 'Not specified'}
- Tool hint: {perception.tool_hint or 'None'}

📋 WORKFLOW GUIDANCE:
For "Find F1 Standings and put in Google Sheet, then email":
1. First: FUNCTION_CALL: search|query="F1 current point standings 2024" (or search_documents)
2. Then: FUNCTION_CALL: create_google_sheet|input.title="F1 Standings"
3. Then: FUNCTION_CALL: add_data_to_sheet|input.sheet_id=<from step 2>|input.data=[[header1,header2],[row1col1,row1col2],...]
4. Then: FUNCTION_CALL: get_sheet_link|input.sheet_id=<from step 2>
5. Then: FUNCTION_CALL: send_email_with_link|to=<use Gmail account email>|subject="F1 Standings"|body="Here is the F1 standings sheet"|sheet_link=<from step 4>
6. Finally: FINAL_ANSWER: [Task completed. Sheet created at <link> and emailed to <email>]

IMPORTANT: For step 5, use the same email address associated with your Gmail account (the one you used for OAuth).

---

📏 CRITICAL Rules:

- 🚫 Do NOT repeat tool calls with the same parameters
- 🔁 If you already called a tool (check memory above), proceed to NEXT step in workflow
- 📄 Use `search` or `search_documents` for finding information
- 📊 Use `create_google_sheet` to create spreadsheet
- 📝 Use `add_data_to_sheet` to add data (format as 2D array: [["Header1","Header2"],["Row1Col1","Row1Col2"]])
- 🔗 Use `get_sheet_link` to get shareable URL
- 📧 Use `send_email_with_link` to send email with sheet link
- ✅ Once all steps complete, return FINAL_ANSWER with summary
- {'⏰ STEP {step_num} OF {max_steps} - You must return FINAL_ANSWER if task cannot be completed or is done!' if is_last_step else ''}
- ❌ NEVER output explanation text — only FUNCTION_CALL or FINAL_ANSWER
- 💡 If stuck or uncertain, return: FINAL_ANSWER: [Progress: <what was done>. Issue: <what's blocking>. Attempted: {used_tools_text if used_tools_text != 'None yet' else 'No tools yet'}]
"""



    try:
        raw = (await model.generate_text(prompt)).strip()
        log("plan", f"LLM output: {raw}")

        for line in raw.splitlines():
            if line.strip().startswith("FUNCTION_CALL:") or line.strip().startswith("FINAL_ANSWER:"):
                return line.strip()

        return "FINAL_ANSWER: [unknown]"

    except Exception as e:
        log("plan", f"⚠️ Planning failed: {e}")
        return "FINAL_ANSWER: [unknown]"

