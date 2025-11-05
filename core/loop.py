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
        self.current_perception = None  # Store current perception for scope limits
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
            
            # Track retry attempts per tool/step (max 3 attempts per step)
            step_retry_count = {}  # {step_number: retry_count}
            max_retries_per_step = 3
            
            # Track completed steps to avoid infinite loops
            completed_steps = set()  # Track which steps completed successfully
            failed_steps = {}  # Track which steps failed and how many times
            
            # Track consecutive failures for short-circuit
            consecutive_failures = 0
            max_consecutive_failures = 3  # Short-circuit after 3 consecutive failures
            
            # Track last tool call to detect loops
            last_tool_call = None
            repeated_calls = 0

            for step in range(max_steps):
                self.context.step = step
                print(f"\n{'='*60}")
                print(f"[loop] Step {step + 1} of {max_steps}")
                print(f"{'='*60}")
                
                # ============================================
                # PHASE 1: PERCEPTION - Understand the question
                # ============================================
                print(f"[phase] PERCEPTION: Understanding user intent...")
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
                            tool_hint="search" if any(word in query.lower() for word in ["find", "search", "get", "show"]) else None,
                            scope_limit=10 if any(word in query.lower() for word in ["standings", "rankings", "leaderboard", "points"]) else None,
                            scope_type="top" if any(word in query.lower() for word in ["standings", "rankings", "leaderboard", "points"]) else None
                        )
                        print(f"[perception] Using fallback perception: {perception.intent}, {perception.tool_hint}")

                # Validate perception before proceeding
                if not hasattr(perception, 'user_input') or not perception.user_input:
                    perception.user_input = query
                
                # Store perception for later use (scope limits, etc.)
                self.current_perception = perception
                
                scope_info = ""
                if hasattr(perception, 'scope_limit') and perception.scope_limit:
                    scope_info = f", Scope: top {perception.scope_limit}"
                print(f"[perception] ✅ Intent: {perception.intent or 'None'}, Hint: {perception.tool_hint or 'None'}{scope_info}")

                # ============================================
                # PHASE 2: MEMORY - Retrieve relevant context
                # ============================================
                print(f"[phase] MEMORY: Retrieving relevant context...")
                retrieved = self.context.memory.retrieve(
                    query=query,
                    top_k=self.context.agent_profile.memory_config["top_k"],
                    type_filter=self.context.agent_profile.memory_config.get("type_filter", None),
                    session_filter=self.context.session_id
                )
                print(f"[memory] ✅ Retrieved {len(retrieved)} memories")

                # ============================================
                # PHASE 3: DECISION - Create execution plan
                # ============================================
                print(f"[phase] DECISION: Creating execution plan...")
                plan = await decide_next_action(
                    context=self.context,
                    perception=perception,
                    memory_items=retrieved,
                    all_tools=self.tools
                )
                print(f"[plan] ✅ {plan}")

                # Check if plan is FINAL_ANSWER (task completed)
                if "FINAL_ANSWER:" in plan:
                    # Verify that email was sent before allowing FINAL_ANSWER
                    used_tools_for_check = [m.tool_name for m in self.context.memory_trace if hasattr(m, 'tool_name') and m.tool_name]
                    email_sent = any("send_email" in tool.lower() for tool in used_tools_for_check)
                    
                    if not email_sent:
                        print(f"[phase] ⚠️ WARNING: Agent tried to return FINAL_ANSWER without sending email!")
                        print(f"[phase] 🔴 FORCING: Agent must send email before completion")
                        # Override the plan to force email sending
                        # Get sheet_link from memory
                        sheet_link = ""
                        for mem in self.context.memory_trace:
                            if hasattr(mem, 'tool_name') and mem.tool_name and "get_sheet_link" in mem.tool_name.lower():
                                if hasattr(mem, 'text') and mem.text:
                                    import re
                                    link_match = re.search(r'https://docs\.google\.com[^\s"]+', str(mem.text))
                                    if link_match:
                                        sheet_link = link_match.group(0)
                                        break
                        
                        if sheet_link:
                            # Force email step - override plan
                            plan = f'FUNCTION_CALL: send_email_with_link|to=""|subject="Data Results"|body="Here is the data sheet with the requested information"|sheet_link="{sheet_link}"'
                            print(f"[phase] 🔄 FORCED: Overriding FINAL_ANSWER to send email first: {plan}")
                            # Continue to execution phase with forced email plan
                        else:
                            print(f"[phase] ⚠️ No sheet link found in memory. Cannot force email.")
                            final_lines = [line for line in plan.splitlines() if line.strip().startswith("FINAL_ANSWER:")]
                            if final_lines:
                                self.context.final_answer = final_lines[-1].strip()
                                print(f"[phase] ✅ COMPLETION: Task completed (no email sent - no sheet link found)")
                                break
                    else:
                        # Email was sent, allow FINAL_ANSWER
                        final_lines = [line for line in plan.splitlines() if line.strip().startswith("FINAL_ANSWER:")]
                        if final_lines:
                            self.context.final_answer = final_lines[-1].strip()
                            print(f"[phase] ✅ COMPLETION: Task completed successfully (email sent)")
                            break
                        else:
                            self.context.final_answer = "FINAL_ANSWER: [result found, but could not extract]"
                            print(f"[phase] ✅ COMPLETION: Task completed (answer extracted)")
                            break
                
                # Force completion if we're at the last step
                if step >= max_steps - 1:
                    print(f"[agent] ⚠️ Reached maximum steps ({max_steps}). Forcing completion.")
                    completed_tools = [m.tool_name for m in self.context.memory_trace if hasattr(m, 'tool_name') and m.tool_name]
                    summary = f"Completed {len(completed_tools)} steps: {', '.join(set(completed_tools))}"
                    self.context.final_answer = f"FINAL_ANSWER: [Task partially completed due to step limit. {summary}]"
                    print(f"[phase] ✅ COMPLETION: Forced completion after {max_steps} steps")
                    break


                # ============================================
                # PHASE 4: EXECUTION - Execute the plan step by step
                # ============================================
                print(f"[phase] EXECUTION: Executing plan...")
                
                try:
                    tool_name, arguments = parse_function_call(plan)
                    
                    # Check if this step has exceeded max retries (track per step, not per tool)
                    step_key = f"step_{step}"
                    retry_count = step_retry_count.get(step_key, 0)
                    
                    if retry_count >= max_retries_per_step:
                        print(f"[agent] ⚠️ Step {step + 1} exceeded max retries ({max_retries_per_step}). Skipping to next step.")
                        failed_steps[step_key] = retry_count
                        consecutive_failures += 1
                        
                        # Short-circuit if too many consecutive failures
                        if consecutive_failures >= max_consecutive_failures:
                            print(f"[agent] ❌ Short-circuit: {consecutive_failures} consecutive failures. Stopping.")
                            completed_tools = [m.tool_name for m in self.context.memory_trace if hasattr(m, 'tool_name') and m.tool_name]
                            summary = f"Completed {len(completed_tools)} steps: {', '.join(set(completed_tools))}"
                            self.context.final_answer = f"FINAL_ANSWER: [Task failed after {consecutive_failures} consecutive failures. {summary}]"
                            break
                        
                        # Move to next step
                        continue
                    
                    # Detect repeated tool calls (potential infinite loop)
                    current_call = f"{tool_name}_{str(arguments)[:50]}"
                    if last_tool_call == current_call:
                        repeated_calls += 1
                        if repeated_calls >= 2:
                            print(f"[agent] ⚠️ Detected infinite loop: same tool call repeated {repeated_calls} times")
                            print(f"[agent] ❌ Forcing completion to break loop")
                            completed_tools = [m.tool_name for m in self.context.memory_trace if hasattr(m, 'tool_name') and m.tool_name]
                            summary = f"Completed {len(completed_tools)} steps: {', '.join(set(completed_tools))}"
                            self.context.final_answer = f"FINAL_ANSWER: [Infinite loop detected. Task stopped. {summary}]"
                            break
                    else:
                        repeated_calls = 0
                        last_tool_call = current_call
                    
                    print(f"[execution] Attempt {retry_count + 1}/{max_retries_per_step}: {tool_name}")

                    if self.tool_expects_input(tool_name):
                        tool_input = {'input': arguments} if not (isinstance(arguments, dict) and 'input' in arguments) else arguments
                    else:
                        tool_input = arguments

                    response = await self.mcp.call_tool(tool_name, tool_input)

                    # ✅ Safe TextContent parsing
                    raw = getattr(response.content, 'text', None)
                    if raw is None:
                        raw = str(response.content)
                    
                    # Handle empty or None raw
                    if not raw:
                        raw = "{}"
                    
                    try:
                        if isinstance(raw, str) and raw.strip().startswith("{"):
                            result_obj = json.loads(raw)
                        else:
                            result_obj = raw
                    except (json.JSONDecodeError, AttributeError):
                        result_obj = {"result": str(raw) if raw else "No response"}

                    result_str = result_obj.get("markdown") if isinstance(result_obj, dict) else str(result_obj) if result_obj else "No result"
                    
                    # Truncate very long results for readability
                    if result_str and len(result_str) > 500:
                        display_result = result_str[:500] + "... [truncated]"
                    else:
                        display_result = result_str
                    print(f"[action] ✅ {tool_name} → {display_result}")

                    # Mark this step as completed
                    step_key = f"step_{step}"
                    completed_steps.add(step_key)
                    step_retry_count[step_key] = 0  # Reset retry count on success
                    
                    # 🧠 Add memory - store full result for retrieval
                    memory_text = f"{tool_name}({arguments}) → {result_str}"
                    if isinstance(result_obj, dict):
                        memory_text += f"\n[STRUCTURED_DATA]: {json.dumps(result_obj)}"
                    
                    memory_item = MemoryItem(
                        text=memory_text,
                        type="tool_output",
                        tool_name=tool_name,
                        user_query=self.context.user_input,
                        tags=[tool_name],
                        session_id=self.context.session_id
                    )
                    self.context.add_memory(memory_item)

                    # Reset failure counters on success
                    consecutive_failures = 0
                    repeated_calls = 0
                    
                    # 🔁 Next query - Provide workflow guidance
                    # Check what tools have been used
                    used_tools = [m.tool_name for m in self.context.memory_trace if hasattr(m, 'tool_name') and m.tool_name]
                    
                    # Get scope limits from current perception
                    scope_limit = None
                    if self.current_perception and hasattr(self.current_perception, 'scope_limit'):
                        scope_limit = self.current_perception.scope_limit
                    
                    workflow_guidance = ""
                    if "search" in tool_name.lower() or "search_documents" in tool_name.lower():
                        # Generic title based on query
                        title_suggestion = "Data Results"
                        if self.current_perception and self.current_perception.entities:
                            title_suggestion = " ".join(self.current_perception.entities[:2]).title()
                        workflow_guidance = f"\n\nNEXT: Create a Google Sheet to store this data. Use: create_google_sheet|input.title=\"{title_suggestion}\""
                    elif "create_google_sheet" in tool_name.lower():
                        # Extract sheet_id from result
                        sheet_id = ""
                        if isinstance(result_obj, dict):
                            sheet_id = result_obj.get("sheet_id") or result_obj.get("sheetId", "")
                        if sheet_id:
                            # Get search results from memory to help format data
                            search_results = ""
                            for mem in self.context.memory_trace:
                                if hasattr(mem, 'tool_name') and mem.tool_name and "search" in mem.tool_name.lower():
                                    # MemoryItem stores result in 'text' attribute
                                    if hasattr(mem, 'text') and mem.text:
                                        search_results = str(mem.text)[:500]
                                        break
                            
                            limit_text = f"top {scope_limit}" if scope_limit else "all available"
                            workflow_guidance = f"\n\n✅ Sheet created successfully! Sheet ID: {sheet_id}\n\nNEXT: Extract data from search results and add to sheet ({limit_text} results).\nUse: add_data_to_sheet|input.sheet_id=\"{sheet_id}\"|input.data=[[\"Header1\",\"Header2\"],[\"Row1Col1\",\"Row1Col2\"],...]\n\nIMPORTANT: Extract relevant data from search results above. Format as 2D array with headers in first row, data rows following. Limit to {scope_limit} rows if scope_limit is set."
                    elif "add_data_to_sheet" in tool_name.lower():
                        # Get sheet_id from arguments
                        sheet_id = ""
                        if isinstance(arguments, dict):
                            if "input" in arguments and isinstance(arguments["input"], dict):
                                sheet_id = arguments["input"].get("sheet_id", "")
                            else:
                                sheet_id = arguments.get("sheet_id", "")
                        if sheet_id:
                            workflow_guidance = f"\n\n✅ Data added to sheet successfully!\n\nNEXT: Get the sheet link using: get_sheet_link|input.sheet_id=\"{sheet_id}\"\n\nIMPORTANT: After getting the link, you MUST send email with the link before completing the task."
                    elif "get_sheet_link" in tool_name.lower():
                        # Extract link from result
                        sheet_link = ""
                        if isinstance(result_obj, dict):
                            sheet_link = result_obj.get("link") or result_obj.get("sheet_url", "") or result_obj.get("sheetUrl", "")
                        if sheet_link:
                            # Get email from .env or use placeholder
                            import os
                            from dotenv import load_dotenv
                            load_dotenv()
                            email_from_env = os.getenv("GMAIL_USER_EMAIL", "").strip()
                            if email_from_env:
                                email_to_use = email_from_env
                            else:
                                email_to_use = ""  # Empty will auto-detect from .env in mcp_server_gmail
                            
                            subject_suggestion = "Data Results"
                            if self.current_perception and self.current_perception.entities:
                                subject_suggestion = " ".join(self.current_perception.entities[:2]).title()
                            
                            # CRITICAL: After getting sheet link, email MUST be sent next - no other steps allowed
                            workflow_guidance = f"\n\n✅ Sheet link retrieved: {sheet_link}\n\n🔴🔴🔴 CRITICAL FINAL STEP: You MUST send email with the sheet link NOW!\n\n🔴 DO NOT DO ANYTHING ELSE - SEND EMAIL IMMEDIATELY!\n\nUse: send_email_with_link|to=\"{email_to_use}\"|subject=\"{subject_suggestion}\"|body=\"Here is the data sheet with the requested information. The Google Sheet link is included below.\"|sheet_link=\"{sheet_link}\"\n\nIMPORTANT: \n- The sheet_link parameter MUST be the exact link from get_sheet_link result: {sheet_link}\n- This is the FINAL step - send email NOW, then return FINAL_ANSWER\n- DO NOT skip this step - email sending is mandatory\n- After sending email successfully, return FINAL_ANSWER with completion message"
                        else:
                            workflow_guidance = f"\n\n⚠️ Failed to get sheet link. Try again or check sheet_id is correct."
                    elif "send_email_with_link" in tool_name.lower() or "send_email" in tool_name.lower():
                        # Email sent successfully - task is complete!
                        # Try to get sheet_link from memory or result
                        email_sheet_link = ""
                        if isinstance(result_obj, dict):
                            email_sheet_link = result_obj.get("link", "") or result_obj.get("sheet_link", "")
                        if not email_sheet_link:
                            # Try to find from memory
                            for mem in self.context.memory_trace:
                                if hasattr(mem, 'tool_name') and mem.tool_name and "get_sheet_link" in mem.tool_name.lower():
                                    if hasattr(mem, 'text') and 'link' in mem.text:
                                        import re
                                        link_match = re.search(r'https://docs\.google\.com[^\s"]+', mem.text)
                                        if link_match:
                                            email_sheet_link = link_match.group(0)
                                            break
                        
                        workflow_guidance = f"\n\n✅ Email sent successfully! Task is complete.\n\nReturn FINAL_ANSWER: [Task completed. Sheet created and emailed successfully. Sheet link: {email_sheet_link if email_sheet_link else 'see email'}]"
                    
                    # Get search results for data extraction context
                    search_context = ""
                    for mem in self.context.memory_trace:
                        if hasattr(mem, 'tool_name') and mem.tool_name and "search" in mem.tool_name.lower():
                            # MemoryItem stores result in 'text' attribute
                            if hasattr(mem, 'text') and mem.text:
                                search_context = f"\n\n📊 Search Results (for data extraction):\n{str(mem.text)[:1500]}{'...' if len(str(mem.text)) > 1500 else ''}"
                                break
                    
                    query = f"""Original user task: {self.context.user_input}

    Tools used so far: {', '.join(set(used_tools))}
    
    Your last tool ({tool_name}) produced this result:

    {result_str[:1000]}{'...' if len(result_str) > 1000 else ''}
    {search_context}
    
    {workflow_guidance}
    
    Step: {step + 2} of {max_steps}
    
    CRITICAL INSTRUCTIONS:
    - If you just created a sheet, you MUST extract relevant data from search results above
    - Look for patterns in search results (e.g., rankings, standings, scores, lists, tables, key-value pairs)
    - Format data as: [["Header1","Header2"],["Row1Col1","Row1Col2"],["Row2Col1","Row2Col2"],...]
    - Limit to {scope_limit} rows if scope_limit is set (currently: {scope_limit or 'no limit'})
    - Extract headers based on the data type found in search results:
      * For rankings/standings: ["Rank","Name","Value"] or ["Position","Item","Score"]
      * For lists/tables: ["Name","Value"] or ["Key","Data"]
      * For time-based data: ["Date","Value"] or ["Time","Metric"]
      * For generic data: ["Column1","Column2","Column3"] based on what's in the results
    - Use the EXACT sheet_id from the create_google_sheet result above (it's in the STRUCTURED_DATA section)
    - Do NOT skip this step - adding data is required!
    
    🔴 MANDATORY WORKFLOW (MUST COMPLETE ALL STEPS):
    1. Search → 2. Create Sheet → 3. Add Data → 4. Get Link → 5. Send Email → 6. FINAL_ANSWER
    
    Check which steps you've completed:
    - Tools used so far: {', '.join(set(used_tools))}
    
    🔴 CRITICAL: You CANNOT return FINAL_ANSWER until you have called send_email_with_link!
    
    Required steps checklist:
    - [ ] search or search_documents (completed if 'search' in tools used)
    - [ ] create_google_sheet (completed if 'create_google_sheet' in tools used)
    - [ ] add_data_to_sheet (completed if 'add_data_to_sheet' in tools used)
    - [ ] get_sheet_link (completed if 'get_sheet_link' in tools used)
    - [ ] send_email_with_link (MUST BE COMPLETED BEFORE FINAL_ANSWER!)
    
    If you just got the sheet link (get_sheet_link), you MUST call send_email_with_link next!
    Do NOT return FINAL_ANSWER until send_email_with_link has been called successfully!
    
    If you have completed ALL 5 steps (including send_email_with_link), return:
    FINAL_ANSWER: [Task completed successfully. Sheet created and emailed to user. Summary: <what was done>]

    Otherwise, return the next FUNCTION_CALL to continue the workflow."""
                except Exception as e:
                    print(f"[error] ❌ Tool execution failed: {e}")
                    
                    # Increment retry count for this step (track per step, not per tool)
                    step_key = f"step_{step}"
                    step_retry_count[step_key] = step_retry_count.get(step_key, 0) + 1
                    retry_count = step_retry_count[step_key]
                    
                    print(f"[execution] ⚠️ Retry count for step {step + 1}: {retry_count}/{max_retries_per_step}")
                    
                    consecutive_failures += 1
                    
                    # Short-circuit if too many consecutive failures
                    if consecutive_failures >= max_consecutive_failures:
                        print(f"[agent] ❌ Short-circuit: {consecutive_failures} consecutive failures. Stopping.")
                        completed_tools = [m.tool_name for m in self.context.memory_trace if hasattr(m, 'tool_name') and m.tool_name]
                        summary = f"Completed {len(completed_tools)} steps: {', '.join(set(completed_tools))}"
                        self.context.final_answer = f"FINAL_ANSWER: [Task failed after {consecutive_failures} consecutive failures. {summary}]"
                        break
                    
                    # If retry limit not reached, continue to next iteration (will retry)
                    if retry_count < max_retries_per_step:
                        print(f"[execution] 🔄 Retrying step {step + 1} (attempt {retry_count + 1}/{max_retries_per_step})...")
                        # Update query to retry with error context
                        query = f"""Original user task: {self.context.user_input}
                        
Error occurred in previous step: {e}

Retry this step with a different approach or provide FINAL_ANSWER if task cannot be completed."""
                        continue  # Retry this step
                    else:
                        print(f"[execution] ❌ Max retries ({max_retries_per_step}) reached for step {step + 1}. Moving to next step.")
                        failed_steps[step_key] = retry_count
                        # Update query to continue to next step
                        query = f"""Original user task: {self.context.user_input}
                        
Previous step failed after {max_retries_per_step} attempts. Continue to next step or provide FINAL_ANSWER if task cannot be completed."""
                        continue  # Move to next step

        except Exception as e:
            print(f"[agent] ❌ Session failed: {e}")
            import traceback
            traceback.print_exc()
            self.context.final_answer = "FINAL_ANSWER: [Agent session failed due to error]"
        
        # ============================================
        # PHASE 5: COMPLETION - Finalize and return
        # ============================================
        print(f"\n{'='*60}")
        print(f"[phase] COMPLETION: Finalizing session...")
        
        if not self.context.final_answer:
            completed_tools = [m.tool_name for m in self.context.memory_trace if hasattr(m, 'tool_name') and m.tool_name]
            summary = f"Completed {len(completed_tools)} steps: {', '.join(set(completed_tools))}"
            self.context.final_answer = f"FINAL_ANSWER: [Task completed. {summary}]"
        
        print(f"[phase] ✅ Final Answer: {self.context.final_answer}")
        print(f"{'='*60}\n")
        
        return self.context.final_answer or "FINAL_ANSWER: [no result]"


