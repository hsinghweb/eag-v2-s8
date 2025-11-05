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
- Scope: {f"top {perception.scope_limit}" if perception.scope_limit else "no limit"} ({perception.scope_type or 'not specified'})

📋 WORKFLOW GUIDANCE (Generic for ANY query):
For ANY user query, follow this standardized workflow:
1. Search: FUNCTION_CALL: search|query="<enhanced query with scope>" (or search_documents)
   - Enhance query with scope: If scope_limit is {perception.scope_limit or 'not specified'}, add "top {perception.scope_limit or 10}" to query
   - Example: If user asks "current standings" with scope_limit=10 → query="current standings top 10"
   - Example: If user asks "latest scores" with scope_limit=20 → query="latest scores top 20"
   - Example: If user asks "stock prices" with scope_limit=15 → query="current stock prices top 15"
2. Create Sheet: FUNCTION_CALL: create_google_sheet|input.title="<relevant title based on query>"
   - Title should reflect the query topic (e.g., "Current Standings", "Latest Scores", "Stock Prices", "Weather Data")
   - Generate title from query entities or keywords
3. Add Data: FUNCTION_CALL: add_data_to_sheet|input.sheet_id=<from step 2>|input.data=[[header1,header2],[row1col1,row1col2],...]
   - CRITICAL: Extract relevant data from search results (look in memory above)
   - Limit to {perception.scope_limit or 10} rows if scope_limit is set
   - Format as 2D array with headers in first row, data rows following
   - Use EXACT sheet_id from create_google_sheet result (check memory - look for sheet_id in STRUCTURED_DATA)
   - Example formats: [["Name","Value"],["Item1","100"],["Item2","200"],...] OR [["Rank","Team","Score"],["1","TeamA","95"],["2","TeamB","87"],...]
   - Headers should match the data type (e.g., Name/Value for generic data, Rank/Team/Score for rankings, Date/Price for stocks)
4. Get Link: FUNCTION_CALL: get_sheet_link|input.sheet_id=<same sheet_id from step 2>
5. Send Email: FUNCTION_CALL: send_email_with_link|to=<email from .env>|subject="<relevant subject>"|body="<relevant body>"|sheet_link=<from step 4>
   - Subject should reflect the query topic (e.g., "Current Standings", "Latest Scores", "Data Results")
   - Body should mention what data is in the sheet
   - Use the email address from .env file (GMAIL_USER_EMAIL)
6. Finally: FINAL_ANSWER: [Task completed. Sheet created at <link> and emailed to <email>]

IMPORTANT: 
- For step 3: Extract ONLY the top {perception.scope_limit or 10} results if scope_limit is set. Limit data rows accordingly.
- For step 5: Use GMAIL_USER_EMAIL from .env file (do NOT use "me" or placeholder)
- ALWAYS use the sheet_id from the create_google_sheet result when calling add_data_to_sheet and get_sheet_link
- This workflow applies to ANY query type - extract data patterns, create relevant headers, and format accordingly

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

