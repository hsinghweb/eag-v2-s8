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
    completed_steps = []
    for m in memory_items:
        if hasattr(m, 'tool_name') and m.tool_name:
            used_tools.append(m.tool_name)
            # Check for completed steps
            if "search" in m.tool_name.lower() or "search_documents" in m.tool_name.lower():
                completed_steps.append("search")
            elif "create_google_sheet" in m.tool_name.lower():
                completed_steps.append("create_sheet")
            elif "add_data_to_sheet" in m.tool_name.lower():
                completed_steps.append("add_data")
            elif "get_sheet_link" in m.tool_name.lower():
                completed_steps.append("get_link")
    
    used_tools_text = ", ".join(set(used_tools)) if used_tools else "None yet"
    completed_steps_text = ", ".join(set(completed_steps)) if completed_steps else "None"
    
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
- ✅ Completed steps (DO NOT retry these - use results from memory): {completed_steps_text}
- Memory from previous steps (contains search results, sheet IDs, etc.): 
{memory_texts}
{tool_context}

🔴 CRITICAL: If a step is marked as "completed" above, DO NOT call that tool again. Use the results from memory instead.

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
   - 🔴 CRITICAL: Only create ONE sheet per session. If a sheet was already created, use the existing sheet_id.
   - Check memory for existing sheet_id before creating a new one
   - Title should reflect the query topic (e.g., "Current Standings", "Latest Scores", "Stock Prices", "Weather Data")
   - Generate title from query entities or keywords
   - ⚠️ DO NOT create multiple sheets - this will cause rate limit errors (429)
3. Add Data: FUNCTION_CALL: add_data_to_sheet|input.sheet_id=<from step 2>|input.data=[[\"Header1\",\"Header2\"],[\"Row1Col1\",\"Row1Col2\"],...]
   - 🔴 CRITICAL: Extract relevant data from search results (look in memory above) - DO NOT use placeholder data
   - Format MUST be: [[\"Header1\",\"Header2\"],[\"DataRow1Col1\",\"DataRow1Col2\"],[\"DataRow2Col1\",\"DataRow2Col2\"],...]
   - First row MUST be headers with quotes: [\"Rank\",\"Name\",\"Score\"] or [\"Name\",\"Value\"]
   - Each data row MUST be a list of quoted strings: [\"1\",\"Team A\",\"95\"] 
   - Limit to {perception.scope_limit or 10} data rows (excluding header) if scope_limit is set
   - Use EXACT sheet_id from create_google_sheet result (check memory - look for sheet_id in STRUCTURED_DATA)
   - Example for rankings: [[\"Rank\",\"Team\",\"Score\"],[\"1\",\"TeamA\",\"95\"],[\"2\",\"TeamB\",\"87\"],[\"3\",\"TeamC\",\"82\"]]
   - Example for generic: [[\"Name\",\"Value\"],[\"Item1\",\"100\"],[\"Item2\",\"200\"],[\"Item3\",\"150\"]]
   - Headers should match the data type (e.g., Name/Value for generic data, Rank/Team/Score for rankings, Date/Price for stocks)
   - ⚠️ If you don't extract real data from search results, the sheet will be blank!
4. Get Link: FUNCTION_CALL: get_sheet_link|input.sheet_id=<same sheet_id from step 2>
5. Finally: FINAL_ANSWER: [Task completed successfully. Google Sheet created with the requested data. Sheet link: <link>]
   - ONLY return FINAL_ANSWER after ALL 4 steps are complete (search, create_google_sheet, add_data_to_sheet, get_sheet_link)
   - The sheet link will automatically be sent to the user via Telegram - no email step needed!

IMPORTANT: 
- 🔴 ALL 4 STEPS ARE MANDATORY: Search → Create Sheet → Add Data → Get Link → FINAL_ANSWER
- For step 3: Extract ONLY the top {perception.scope_limit or 10} results if scope_limit is set. Limit data rows accordingly.
- For step 4: After getting the sheet link, you can immediately return FINAL_ANSWER
- ALWAYS use the sheet_id from the create_google_sheet result when calling add_data_to_sheet and get_sheet_link
- The sheet link will be automatically included in the Telegram response - no need to send email
- This workflow applies to ANY query type - extract data patterns, create relevant headers, and format accordingly

---

📏 CRITICAL Rules:

- 🚫 Do NOT repeat tool calls with the same parameters
- 🔁 If you already called a tool (check memory above), proceed to NEXT step in workflow
- 📄 Use `search` or `search_documents` for finding information
- 📊 Use `create_google_sheet` to create spreadsheet
- 📝 Use `add_data_to_sheet` to add data (format as 2D array: [["Header1","Header2"],["Row1Col1","Row1Col2"]])
- 🔗 Use `get_sheet_link` to get shareable URL
- ✅ Once ALL 4 steps complete (search, create_google_sheet, add_data_to_sheet, get_sheet_link), return FINAL_ANSWER with summary
- 📱 The sheet link will automatically be sent to the user via Telegram - no email step needed
- {'⏰ STEP {step_num} OF {max_steps} - You must return FINAL_ANSWER if task cannot be completed or is done!' if is_last_step else ''}
- ❌ NEVER output explanation text — only FUNCTION_CALL or FINAL_ANSWER
- 💡 If stuck or uncertain, return: FINAL_ANSWER: [Progress: <what was done>. Issue: <what's blocking>. Attempted: {used_tools_text if used_tools_text != 'None yet' else 'No tools yet'}]
"""



    try:
        raw = (await model.generate_text(prompt, max_retries=3, prompt_type="decision")).strip()
        log("plan", f"LLM output: {raw}")

        for line in raw.splitlines():
            if line.strip().startswith("FUNCTION_CALL:") or line.strip().startswith("FINAL_ANSWER:"):
                return line.strip()

        return "FINAL_ANSWER: [unknown]"

    except Exception as e:
        log("plan", f"⚠️ Planning failed: {e}")
        return "FINAL_ANSWER: [unknown]"

