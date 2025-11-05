# core/loop.py

import asyncio
import time
from core.context import AgentContext
from core.session import MultiMCP
from core.strategy import decide_next_action
from modules.perception import extract_perception, PerceptionResult
from modules.action import ToolCallResult, parse_function_call
from modules.memory import MemoryItem
from modules.logger import AgentLogger, set_logger, get_logger
import json


class AgentLoop:
    def __init__(self, user_input: str, dispatcher: MultiMCP):
        self.context = AgentContext(user_input)
        self.mcp = dispatcher
        self.current_perception = None  # Store current perception for scope limits
        self.tools = dispatcher.get_all_tools()
        self._pending_sheet_link = None  # Store sheet_link after get_sheet_link
        self._logger = AgentLogger(self.context.session_id)
        set_logger(self._logger)
        
        # Workflow step tracking
        self.workflow_steps = {
            'search_completed': False,
            'sheet_created': False,
            'data_added': False,
            'link_retrieved': False
        }
        
        # Track created sheet to prevent multiple creations
        self._created_sheet_id = None
        self._created_sheet_url = None
        
        # Track tool call attempts to prevent excessive API calls
        self._tool_call_attempts = {}  # {tool_name: attempt_count}
        self._max_tool_attempts = 3  # Max 3 attempts per tool

    def tool_expects_input(self, tool_name: str) -> bool:
        tool = next((t for t in self.tools if getattr(t, "name", None) == tool_name), None)
        if not tool:
            return False
        parameters = getattr(tool, "parameters", {})
        return list(parameters.keys()) == ["input"]
    
    def verify_search_completed(self) -> tuple[bool, str]:
        """Verify that search step is completed"""
        for mem in self.context.memory_trace:
            if hasattr(mem, 'tool_name') and mem.tool_name:
                if "search" in mem.tool_name.lower():
                    if hasattr(mem, 'text') and mem.text and len(str(mem.text)) > 10:
                        self.workflow_steps['search_completed'] = True
                        return True, "Search completed with results"
        return False, "Search not completed - no search results found"
    
    def verify_sheet_created(self) -> tuple[bool, str]:
        """Verify that sheet creation is completed"""
        # Check if we already have a sheet_id tracked
        if self._created_sheet_id:
            self.workflow_steps['sheet_created'] = True
            return True, f"Sheet already created: {self._created_sheet_id}"
        
        # Check memory for sheet creation
        for mem in self.context.memory_trace:
            if hasattr(mem, 'tool_name') and mem.tool_name:
                if "create_google_sheet" in mem.tool_name.lower():
                    if hasattr(mem, 'text') and mem.text:
                        import json
                        import re
                        # Try to extract sheet_id
                        text = str(mem.text)
                        json_match = re.search(r'\{"sheet_id":\s*"([^"]+)"', text)
                        if json_match:
                            sheet_id = json_match.group(1)
                            self._created_sheet_id = sheet_id
                            self.workflow_steps['sheet_created'] = True
                            return True, f"Sheet created successfully: {sheet_id}"
                        elif "sheet_id" in text.lower():
                            # Try to extract from JSON in text
                            try:
                                json_data = json.loads(text)
                                if isinstance(json_data, dict) and "sheet_id" in json_data:
                                    sheet_id = json_data["sheet_id"]
                                    self._created_sheet_id = sheet_id
                                    self.workflow_steps['sheet_created'] = True
                                    return True, f"Sheet created successfully: {sheet_id}"
                            except:
                                pass
        return False, "Sheet creation not verified - no sheet_id found"
    
    def get_created_sheet_id(self) -> str:
        """Get the sheet_id of the created sheet"""
        return self._created_sheet_id
    
    def verify_data_added(self) -> tuple[bool, str]:
        """Verify that data was added to sheet"""
        for mem in self.context.memory_trace:
            if hasattr(mem, 'tool_name') and mem.tool_name:
                if "add_data_to_sheet" in mem.tool_name.lower():
                    if hasattr(mem, 'text') and mem.text:
                        text = str(mem.text)
                        # Check for success indicators
                        if "success" in text.lower() or "updated_cells" in text.lower():
                            self.workflow_steps['data_added'] = True
                            return True, "Data added successfully"
        return False, "Data addition not verified - no success confirmation"
    
    def verify_link_retrieved(self) -> tuple[bool, str]:
        """Verify that sheet link was retrieved"""
        if self._pending_sheet_link:
            self.workflow_steps['link_retrieved'] = True
            return True, f"Link retrieved: {self._pending_sheet_link}"
        
        # Check memory for link
        for mem in self.context.memory_trace:
            if hasattr(mem, 'tool_name') and mem.tool_name:
                if "get_sheet_link" in mem.tool_name.lower():
                    if hasattr(mem, 'text') and mem.text:
                        import re
                        link_match = re.search(r'https://docs\.google\.com/spreadsheets/d/[^\s"<>\'\)]+', str(mem.text))
                        if link_match:
                            self.workflow_steps['link_retrieved'] = True
                            return True, f"Link retrieved: {link_match.group(0)}"
        return False, "Link retrieval not verified - no sheet link found"
    
    def get_next_required_step(self) -> tuple[str, str]:
        """Get the next required step in the workflow"""
        if not self.workflow_steps['search_completed']:
            return "search", "Search for information first"
        if not self.workflow_steps['sheet_created']:
            return "create_sheet", "Create Google Sheet"
        if not self.workflow_steps['data_added']:
            return "add_data", "Add data to sheet"
        if not self.workflow_steps['link_retrieved']:
            return "get_link", "Get sheet link"
        return "final_answer", "All steps completed - return FINAL_ANSWER"

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
                self._logger.log_workflow_step(step + 1, "perception", "started")
                start_time = time.time()
                perception_raw = await extract_perception(query)
                duration_ms = (time.time() - start_time) * 1000
                self._logger.log_workflow_step(step + 1, "perception", "completed", f"Duration: {duration_ms:.2f}ms")


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
                self._logger.log_workflow_step(step + 1, "memory", "started")
                retrieved = self.context.memory.retrieve(
                    query=query,
                    top_k=self.context.agent_profile.memory_config["top_k"],
                    type_filter=self.context.agent_profile.memory_config.get("type_filter", None),
                    session_filter=self.context.session_id
                )
                print(f"[memory] ✅ Retrieved {len(retrieved)} memories")
                self._logger.log_workflow_step(step + 1, "memory", "completed", f"Retrieved {len(retrieved)} memories")

                # ============================================
                # PHASE 3: DECISION - Create execution plan
                # ============================================
                print(f"[phase] DECISION: Creating execution plan...")
                self._logger.log_workflow_step(step + 1, "decision", "started")
                
                # Verify workflow steps before planning
                next_step, next_step_desc = self.get_next_required_step()
                if next_step != "final_answer":
                    print(f"[workflow] ⚠️ Next required step: {next_step} - {next_step_desc}")
                    self._logger.log_verification("workflow_step", False, f"Next required: {next_step}")
                else:
                    print(f"[workflow] ✅ All workflow steps completed")
                    self._logger.log_verification("workflow_step", True, "All steps completed")
                
                # Generate plan normally (no email step needed)
                start_time = time.time()
                plan = await decide_next_action(
                    context=self.context,
                    perception=perception,
                    memory_items=retrieved,
                    all_tools=self.tools
                )
                duration_ms = (time.time() - start_time) * 1000
                print(f"[plan] ✅ {plan}")
                self._logger.log_workflow_step(step + 1, "decision", "completed", f"Plan: {plan[:100]}... Duration: {duration_ms:.2f}ms")

                # Check if plan is FINAL_ANSWER (task completed)
                if "FINAL_ANSWER:" in plan:
                    # Verify all workflow steps are completed before finalizing
                    all_verified = all([
                        self.workflow_steps['search_completed'],
                        self.workflow_steps['sheet_created'],
                        self.workflow_steps['data_added'],
                        self.workflow_steps['link_retrieved']
                    ])
                    
                    if not all_verified:
                        missing_steps = [step for step, completed in self.workflow_steps.items() if not completed]
                        print(f"[workflow] ⚠️ Cannot finalize - missing steps: {missing_steps}")
                        self._logger.log_verification("final_answer", False, f"Missing steps: {missing_steps}")
                        # Continue to next iteration to complete missing steps
                        query = f"""Original user task: {self.context.user_input}
                        
You tried to return FINAL_ANSWER but the following workflow steps are not completed:
{', '.join(missing_steps)}

MANDATORY WORKFLOW (must complete ALL steps):
1. Search → 2. Create Sheet → 3. Add Data → 4. Get Link → 5. FINAL_ANSWER

Complete the missing steps before returning FINAL_ANSWER."""
                        continue
                    
                    # All steps verified - extract FINAL_ANSWER and STOP
                    final_lines = [line for line in plan.splitlines() if line.strip().startswith("FINAL_ANSWER:")]
                    if final_lines:
                        self.context.final_answer = final_lines[-1].strip()
                        print(f"[phase] ✅ COMPLETION: Task completed successfully - all steps verified")
                        print(f"[workflow] 🛑 Stopping agent loop - task complete")
                        self._logger.log_verification("final_answer", True, "All workflow steps completed")
                        break  # Exit loop immediately
                    else:
                        # Extract sheet link if available
                        sheet_link = self._pending_sheet_link or self._created_sheet_url
                        if not sheet_link and self._created_sheet_id:
                            sheet_link = f"https://docs.google.com/spreadsheets/d/{self._created_sheet_id}/edit"
                        
                        if sheet_link:
                            self.context.final_answer = f"FINAL_ANSWER: [Task completed successfully. Google Sheet created with the requested data. Sheet link: {sheet_link}]"
                        else:
                            self.context.final_answer = "FINAL_ANSWER: [Task completed successfully. Google Sheet created with the requested data.]"
                        print(f"[phase] ✅ COMPLETION: Task completed (answer extracted)")
                        print(f"[workflow] 🛑 Stopping agent loop - task complete")
                        break  # Exit loop immediately
                
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
                    self._logger.log_workflow_step(step + 1, "execution", "started", f"Tool: {tool_name}")

                    # Prevent multiple sheet creation - check BEFORE calling tool
                    if "create_google_sheet" in tool_name.lower():
                        if self._created_sheet_id:
                            print(f"[workflow] ⚠️ Sheet already exists (ID: {self._created_sheet_id}). Preventing duplicate creation.")
                            # Simulate successful response with existing sheet_id
                            result_obj = {
                                "sheet_id": self._created_sheet_id,
                                "sheet_url": self._created_sheet_url or f"https://docs.google.com/spreadsheets/d/{self._created_sheet_id}/edit",
                                "message": "Using existing sheet (duplicate creation prevented)"
                            }
                            result_str = json.dumps(result_obj)
                            print(f"[action] ✅ {tool_name} → Using existing sheet: {self._created_sheet_id}")
                            
                            # Add to memory as if tool was called
                            memory_text = f"{tool_name}({arguments}) → {result_str}"
                            memory_item = MemoryItem(
                                text=memory_text,
                                type="tool_output",
                                tool_name=tool_name,
                                user_query=self.context.user_input,
                                tags=[tool_name],
                                session_id=self.context.session_id
                            )
                            self.context.add_memory(memory_item)
                            
                            # Mark step as completed
                            step_key = f"step_{step}"
                            completed_steps.add(step_key)
                            step_retry_count[step_key] = 0
                            
                            # Update query to continue with existing sheet
                            query = f"""Original user task: {self.context.user_input}

⚠️ You tried to create a new sheet, but a sheet already exists (ID: {self._created_sheet_id}).
Use the EXISTING sheet_id to add data: add_data_to_sheet|input.sheet_id="{self._created_sheet_id}"|input.data=[[...]]

Do NOT create another sheet - this will cause rate limit errors."""
                            continue
                    
                    # Check tool call attempts to prevent excessive API calls
                    tool_attempt_key = f"{tool_name}_{str(arguments)[:50]}"
                    if tool_attempt_key not in self._tool_call_attempts:
                        self._tool_call_attempts[tool_attempt_key] = 0
                    
                    self._tool_call_attempts[tool_attempt_key] += 1
                    attempt_count = self._tool_call_attempts[tool_attempt_key]
                    
                    if attempt_count > self._max_tool_attempts:
                        error_msg = f"Tool '{tool_name}' exceeded maximum attempts ({self._max_tool_attempts}). This may be due to rate limits (429) or persistent errors. Please try again later."
                        print(f"[workflow] ❌ {error_msg}")
                        self._logger.log_error("tool_max_attempts_exceeded", error_msg)
                        raise Exception(error_msg)

                    if self.tool_expects_input(tool_name):
                        tool_input = {'input': arguments} if not (isinstance(arguments, dict) and 'input' in arguments) else arguments
                    else:
                        tool_input = arguments

                    # Log tool call
                    start_time = time.time()
                    
                    # Identify DuckDuckGoSearcher tool calls
                    tool_display_name = tool_name
                    if tool_name == "search" and "query" in str(tool_input).lower():
                        tool_display_name = "DuckDuckGoSearcher (web_search)"
                        print(f"[tool] 🔍 Calling DuckDuckGoSearcher for web search: {tool_input}")
                    
                    try:
                        response = await self.mcp.call_tool(tool_name, tool_input)
                        duration_ms = (time.time() - start_time) * 1000
                        self._logger.log_tool_call(tool_display_name, tool_input, "success", duration_ms)
                        
                        # Reset attempt count on success
                        self._tool_call_attempts[tool_attempt_key] = 0
                        
                        # Special logging for DuckDuckGoSearcher
                        if tool_name == "search":
                            print(f"[DuckDuckGoSearcher] ✅ Web search completed via tool call (duration: {duration_ms:.2f}ms)")
                    except Exception as tool_error:
                        duration_ms = (time.time() - start_time) * 1000
                        error_msg = str(tool_error)
                        
                        # Check for rate limit errors (429)
                        is_rate_limit = "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg.upper() or "rate limit" in error_msg.lower()
                        if is_rate_limit:
                            print(f"[workflow] ⚠️ Rate limit detected (429) for tool '{tool_name}'. Attempt {attempt_count}/{self._max_tool_attempts}")
                            self._logger.log_error("rate_limit_error", f"Tool: {tool_name}, Attempt: {attempt_count}")
                            if attempt_count >= self._max_tool_attempts:
                                raise Exception(f"Rate limit exceeded after {self._max_tool_attempts} attempts for '{tool_name}'. Please wait before trying again.")
                        
                        # Check for 404 errors (sheet not found)
                        is_404 = "404" in error_msg or "not found" in error_msg.lower()
                        if is_404 and "create_google_sheet" not in tool_name.lower():
                            print(f"[workflow] ⚠️ Resource not found (404) - Sheet may have been deleted or sheet_id is incorrect")
                            self._logger.log_error("resource_not_found", f"Tool: {tool_name}, Error: {error_msg}")
                            # If sheet_id is wrong, try using stored sheet_id
                            if "add_data_to_sheet" in tool_name.lower() and self._created_sheet_id:
                                print(f"[workflow] 🔄 Attempting to use stored sheet_id: {self._created_sheet_id}")
                                # Will be retried with correct sheet_id in next iteration
                        
                        self._logger.log_tool_call(tool_display_name, tool_input, None, duration_ms, error_msg)
                        self._logger.log_error("tool_execution_error", error_msg)
                        
                        # Special logging for DuckDuckGoSearcher errors
                        if tool_name == "search":
                            print(f"[DuckDuckGoSearcher] ❌ Web search failed: {error_msg}")
                        
                        # If max attempts reached, don't raise - let retry logic handle it
                        if attempt_count >= self._max_tool_attempts:
                            raise Exception(f"Tool '{tool_name}' failed after {self._max_tool_attempts} attempts. Last error: {error_msg}")
                        raise

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

                    # Verify workflow step completion
                    if "search" in tool_name.lower() or "search_documents" in tool_name.lower():
                        verified, details = self.verify_search_completed()
                        self._logger.log_verification("search", verified, details)
                        if verified:
                            print(f"[workflow] ✅ Search step verified: {details}")
                    
                    elif "create_google_sheet" in tool_name.lower():
                        # Extract and store sheet_id immediately from result
                        if isinstance(result_obj, dict):
                            sheet_id = result_obj.get("sheet_id") or result_obj.get("sheetId", "")
                            if sheet_id:
                                self._created_sheet_id = sheet_id
                                self._created_sheet_url = result_obj.get("sheet_url") or result_obj.get("sheetUrl", "")
                                self.workflow_steps['sheet_created'] = True
                                print(f"[workflow] ✅ Sheet created and stored: {sheet_id}")
                        
                        verified, details = self.verify_sheet_created()
                        self._logger.log_verification("create_sheet", verified, details)
                        if verified:
                            print(f"[workflow] ✅ Sheet creation verified: {details}")
                        else:
                            print(f"[workflow] ⚠️ Sheet creation not verified: {details}")
                    
                    elif "add_data_to_sheet" in tool_name.lower():
                        verified, details = self.verify_data_added()
                        self._logger.log_verification("add_data", verified, details)
                        if verified:
                            print(f"[workflow] ✅ Data addition verified: {details}")
                        else:
                            print(f"[workflow] ⚠️ Data addition not verified: {details}")
                    
                    elif "get_sheet_link" in tool_name.lower():
                        verified, details = self.verify_link_retrieved()
                        self._logger.log_verification("get_link", verified, details)
                        if verified:
                            print(f"[workflow] ✅ Link retrieval verified: {details}")
                        else:
                            print(f"[workflow] ⚠️ Link retrieval not verified: {details}")

                    # Mark this step as completed
                    step_key = f"step_{step}"
                    completed_steps.add(step_key)
                    step_retry_count[step_key] = 0  # Reset retry count on success
                    
                    # Log step completion
                    next_step, next_step_desc = self.get_next_required_step()
                    self._logger.log_step_completion(tool_name, True, next_step)
                    
                    # EARLY TERMINATION: Check if all workflow steps are complete
                    all_steps_complete = all([
                        self.workflow_steps['search_completed'],
                        self.workflow_steps['sheet_created'],
                        self.workflow_steps['data_added'],
                        self.workflow_steps['link_retrieved']
                    ])
                    
                    if all_steps_complete:
                        print(f"[workflow] 🎉 All workflow steps completed! Preparing FINAL_ANSWER...")
                        self._logger.log_verification("all_steps_complete", True, "All workflow steps verified")
                        
                        # Construct final answer with sheet link
                        sheet_link = self._pending_sheet_link or self._created_sheet_url
                        if not sheet_link and self._created_sheet_id:
                            sheet_link = f"https://docs.google.com/spreadsheets/d/{self._created_sheet_id}/edit"
                        
                        if sheet_link:
                            self.context.final_answer = f"FINAL_ANSWER: [Task completed successfully. Google Sheet created with the requested data. Sheet link: {sheet_link}]"
                        else:
                            self.context.final_answer = f"FINAL_ANSWER: [Task completed successfully. Google Sheet created with the requested data.]"
                        
                        print(f"[workflow] ✅ Task completed - stopping agent loop immediately")
                        break  # Exit loop immediately
                    
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
                        # Extract sheet_id from result and store it
                        sheet_id = ""
                        sheet_url = ""
                        if isinstance(result_obj, dict):
                            sheet_id = result_obj.get("sheet_id") or result_obj.get("sheetId", "")
                            sheet_url = result_obj.get("sheet_url") or result_obj.get("sheetUrl", "")
                        
                        # Store sheet_id to prevent duplicate creation
                        if sheet_id:
                            self._created_sheet_id = sheet_id
                            self._created_sheet_url = sheet_url
                            print(f"[workflow] 📊 Sheet ID stored: {sheet_id} (preventing duplicate creation)")
                            
                            # Get search results from memory to help format data
                            search_results = ""
                            for mem in self.context.memory_trace:
                                if hasattr(mem, 'tool_name') and mem.tool_name and "search" in mem.tool_name.lower():
                                    # MemoryItem stores result in 'text' attribute
                                    if hasattr(mem, 'text') and mem.text:
                                        search_results = str(mem.text)[:500]
                                        break
                            
                            limit_text = f"top {scope_limit}" if scope_limit else "all available"
                            workflow_guidance = f"\n\n✅ Sheet created successfully! Sheet ID: {sheet_id}\n\n⚠️ IMPORTANT: Do NOT create another sheet. Use this sheet_id: {sheet_id}\n\nNEXT: Extract data from search results and add to sheet ({limit_text} results).\n\n🔴 CRITICAL FORMATTING INSTRUCTIONS:\n- Use: add_data_to_sheet|input.sheet_id=\"{sheet_id}\"|input.data=[[\"Header1\",\"Header2\"],[\"Row1Col1\",\"Row1Col2\"],[\"Row2Col1\",\"Row2Col2\"]]\n- Format MUST be: [[\"Header1\",\"Header2\"],[\"DataRow1Col1\",\"DataRow1Col2\"],[\"DataRow2Col1\",\"DataRow2Col2\"],...]\n- First row MUST be headers (e.g., [\"Rank\",\"Name\",\"Score\"])\n- Each row MUST be a list of strings: [\"Value1\",\"Value2\",\"Value3\"]\n- Extract data from search results above - DO NOT use placeholder data\n- Limit to {scope_limit} data rows (excluding header) if scope_limit is set\n- Example for 3 items: [[\"Rank\",\"Name\",\"Points\"],[\"1\",\"Team A\",\"95\"],[\"2\",\"Team B\",\"87\"],[\"3\",\"Team C\",\"82\"]]\n\n⚠️ If you don't extract real data, the sheet will be blank!"
                    elif "add_data_to_sheet" in tool_name.lower():
                        # Get sheet_id from arguments - use stored sheet_id if available
                        sheet_id = self._created_sheet_id or ""
                        if not sheet_id:
                            if isinstance(arguments, dict):
                                if "input" in arguments and isinstance(arguments["input"], dict):
                                    sheet_id = arguments["input"].get("sheet_id", "")
                                else:
                                    sheet_id = arguments.get("sheet_id", "")
                        
                        # If we have a stored sheet_id, ensure it matches
                        if self._created_sheet_id and sheet_id != self._created_sheet_id:
                            print(f"[workflow] ⚠️ Sheet ID mismatch: using stored ID {self._created_sheet_id} instead of {sheet_id}")
                            sheet_id = self._created_sheet_id
                        
                        if sheet_id:
                            workflow_guidance = f"\n\n✅ Data added to sheet successfully!\n\nNEXT: Get the sheet link using: get_sheet_link|input.sheet_id=\"{sheet_id}\"\n\nIMPORTANT: Use the EXACT sheet_id: {sheet_id}\nAfter getting the link, you can return FINAL_ANSWER. The link will be sent to the user via Telegram."
                    elif "get_sheet_link" in tool_name.lower():
                        # Extract link from result - use stored sheet_id if needed
                        sheet_link = ""
                        if isinstance(result_obj, dict):
                            sheet_link = result_obj.get("link") or result_obj.get("sheet_url", "") or result_obj.get("sheetUrl", "")
                        
                        # If link not found but we have stored sheet_url, use it
                        if not sheet_link and self._created_sheet_url:
                            sheet_link = self._created_sheet_url
                            print(f"[workflow] Using stored sheet URL: {sheet_link}")
                        
                        # If still no link, construct from stored sheet_id
                        if not sheet_link and self._created_sheet_id:
                            sheet_link = f"https://docs.google.com/spreadsheets/d/{self._created_sheet_id}/edit"
                            print(f"[workflow] Constructed sheet link from stored sheet_id: {sheet_link}")
                        
                        if sheet_link:
                            # Store sheet_link for Telegram response
                            self._pending_sheet_link = sheet_link
                            self.workflow_steps['link_retrieved'] = True
                            
                            # After getting sheet link, task is complete - return FINAL_ANSWER IMMEDIATELY
                            workflow_guidance = f"\n\n✅ Sheet link retrieved successfully: {sheet_link}\n\n🎉 ALL STEPS COMPLETE! Return FINAL_ANSWER immediately.\n\nReturn FINAL_ANSWER: [Task completed successfully. Google Sheet created with the requested data. Sheet link: {sheet_link}]\n\nThe sheet link will be sent to the user via Telegram."
                        else:
                            workflow_guidance = f"\n\n⚠️ Failed to get sheet link. Try again or check sheet_id is correct."
                    
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
    - 🔴 Format data EXACTLY as: [["Header1","Header2"],["Row1Col1","Row1Col2"],["Row2Col1","Row2Col2"],...]
    - 🔴 ALL values MUST be quoted strings: [["Rank","Name","Score"],["1","Team A","95"],["2","Team B","87"]]
    - 🔴 First row MUST be headers: [["Rank","Name","Points"],...]
    - 🔴 Each subsequent row MUST be data: ["1","Team A","95"]
    - Limit to {scope_limit} data rows (excluding header) if scope_limit is set (currently: {scope_limit or 'no limit'})
    - Extract headers based on the data type found in search results:
      * For rankings/standings: ["Rank","Name","Value"] or ["Position","Item","Score"]
      * For lists/tables: ["Name","Value"] or ["Key","Data"]
      * For time-based data: ["Date","Value"] or ["Time","Metric"]
      * For generic data: ["Column1","Column2","Column3"] based on what's in the results
    - Use the EXACT sheet_id from the create_google_sheet result above (it's in the STRUCTURED_DATA section)
    - Do NOT skip this step - adding data is required!
    - ⚠️ If you don't extract real data from search results, the sheet will remain blank!
    
    🔴 MANDATORY WORKFLOW (MUST COMPLETE ALL STEPS):
    1. Search → 2. Create Sheet → 3. Add Data → 4. Get Link → 5. FINAL_ANSWER
    
    Check which steps you've completed:
    - Tools used so far: {', '.join(set(used_tools))}
    
    Required steps checklist:
    - [ ] search or search_documents (completed if 'search' in tools used)
    - [ ] create_google_sheet (completed if 'create_google_sheet' in tools used)
    - [ ] add_data_to_sheet (completed if 'add_data_to_sheet' in tools used)
    - [ ] get_sheet_link (completed if 'get_sheet_link' in tools used)
    
    🔴 IF YOU JUST CALLED get_sheet_link:
    - Task is complete! Return FINAL_ANSWER with a summary
    - The sheet link will automatically be sent to the user via Telegram
    - Format: FINAL_ANSWER: [Task completed successfully. Google Sheet created with the requested data. Sheet link: <link>]
    
    If you have completed ALL 4 steps (search, create_google_sheet, add_data_to_sheet, get_sheet_link), return:
    FINAL_ANSWER: [Task completed successfully. Google Sheet created with the requested data. Summary: <what was done>]

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
            self._logger.log_error("session_failed", str(e), traceback.format_exc())
            traceback.print_exc()
            self.context.final_answer = "FINAL_ANSWER: [Agent session failed due to error]"
        
        # ============================================
        # PHASE 5: COMPLETION - Finalize and return
        # ============================================
        print(f"\n{'='*60}")
        print(f"[phase] COMPLETION: Finalizing session...")
        self._logger.log_workflow_step(999, "completion", "started")
        
        if not self.context.final_answer:
            completed_tools = [m.tool_name for m in self.context.memory_trace if hasattr(m, 'tool_name') and m.tool_name]
            summary = f"Completed {len(completed_tools)} steps: {', '.join(set(completed_tools))}"
            self.context.final_answer = f"FINAL_ANSWER: [Task completed. {summary}]"
        
        # Log final workflow status
        workflow_status = {
            'search': self.workflow_steps['search_completed'],
            'sheet_created': self.workflow_steps['sheet_created'],
            'data_added': self.workflow_steps['data_added'],
            'link_retrieved': self.workflow_steps['link_retrieved']
        }
        self._logger.log_workflow_step(999, "completion", "completed", f"Workflow status: {workflow_status}")
        
        print(f"[phase] ✅ Final Answer: {self.context.final_answer}")
        print(f"[workflow] Final Status: {workflow_status}")
        print(f"{'='*60}\n")
        
        return self.context.final_answer or "FINAL_ANSWER: [no result]"


