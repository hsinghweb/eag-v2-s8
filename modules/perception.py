from typing import List, Optional
from pydantic import BaseModel
import os
import re
import json
from dotenv import load_dotenv
from modules.model_manager import ModelManager
from modules.tools import summarize_tools

model = ModelManager()
tool_context = summarize_tools(model.get_all_tools()) if hasattr(model, "get_all_tools") else ""


class PerceptionResult(BaseModel):
    user_input: str
    intent: Optional[str]
    entities: List[str] = []
    tool_hint: Optional[str] = None


async def extract_perception(user_input: str) -> PerceptionResult:
    """
    Uses LLMs to extract structured info:
    - intent: user’s high-level goal
    - entities: keywords or values
    - tool_hint: likely MCP tool name (optional)
    """

    prompt = f"""
You are an AI that extracts structured facts from user input.

Available tools: {tool_context}

Input: "{user_input}"

CRITICAL: Return ONLY valid JSON (no markdown, no explanations, no code blocks).
Format: {{"intent": "...", "entities": ["keyword1", "keyword2"], "tool_hint": "...", "user_input": "..."}}

Required keys:
- intent: (brief phrase about what the user wants)
- entities: a list of strings representing keywords or values (e.g., ["F1", "standings"])
- tool_hint: (name of the MCP tool that might be useful, or null)
- user_input: same as the input above

Example output: {{"intent": "search for F1 standings", "entities": ["F1", "standings"], "tool_hint": "search", "user_input": "Find F1 standings"}}

OUTPUT ONLY THE JSON DICTIONARY, NOTHING ELSE.
"""

    try:
        response = await model.generate_text(prompt)

        # Clean up raw if wrapped in markdown-style ```json
        raw = response.strip()
        if not raw or raw.lower() in ["none", "null", "undefined"]:
            raise ValueError("Empty or null model output")

        # Clean and parse - try multiple strategies
        clean = re.sub(r"^```json|```$|```python", "", raw, flags=re.MULTILINE).strip()
        # Remove any markdown code blocks
        clean = re.sub(r"^```.*?```", "", clean, flags=re.MULTILINE | re.DOTALL).strip()
        
        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean)
        if json_match:
            clean = json_match.group(0)
        
        parsed = {}
        try:
            parsed = json.loads(clean)
        except json.JSONDecodeError as json_error:
            print(f"[perception] JSON parsing failed: {json_error}")
            print(f"[perception] Raw response (first 200 chars): {raw[:200]}")
            # Try to extract key-value pairs manually
            intent_match = re.search(r'"intent"\s*:\s*"([^"]*)"', clean)
            tool_hint_match = re.search(r'"tool_hint"\s*:\s*"([^"]*)"', clean)
            if intent_match:
                parsed["intent"] = intent_match.group(1)
            if tool_hint_match:
                parsed["tool_hint"] = tool_hint_match.group(1)
            # Default fallback
            parsed.setdefault("entities", [])

        # Ensure Keys with defaults
        if not isinstance(parsed, dict):
            parsed = {}
        
        # Set defaults
        parsed.setdefault("user_input", user_input)
        parsed.setdefault("intent", None)
        parsed.setdefault("tool_hint", None)
        parsed.setdefault("entities", [])
        
        # Fix common issues
        if isinstance(parsed.get("entities"), dict):
            parsed["entities"] = list(parsed["entities"].values())
        elif not isinstance(parsed.get("entities"), list):
            parsed["entities"] = []
        
        # Extract tool hint from user input if not provided
        if not parsed.get("tool_hint") and user_input:
            if "search" in user_input.lower() or "find" in user_input.lower():
                parsed["tool_hint"] = "search"
            elif "sheet" in user_input.lower() or "google" in user_input.lower():
                parsed["tool_hint"] = "create_google_sheet"
            elif "email" in user_input.lower() or "gmail" in user_input.lower():
                parsed["tool_hint"] = "send_email"

        parsed["user_input"] = user_input  # overwrite or insert safely
        return PerceptionResult(**parsed)


    except Exception as e:
        print(f"[perception] ⚠️ LLM perception failed: {e}")
        return PerceptionResult(user_input=user_input)
