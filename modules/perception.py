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
    scope_limit: Optional[int] = None  # e.g., top 10, top 20, etc.
    scope_type: Optional[str] = None  # e.g., "top", "recent", "current", "latest"


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
Format: {{"intent": "...", "entities": ["keyword1", "keyword2"], "tool_hint": "...", "user_input": "...", "scope_limit": 10, "scope_type": "top"}}

Required keys:
- intent: (brief phrase about what the user wants)
- entities: a list of strings representing keywords or values (e.g., ["standings", "rankings"], ["scores", "results"], ["prices", "stocks"])
- tool_hint: (name of the MCP tool that might be useful, or null)
- user_input: same as the input above
- scope_limit: (number indicating how many results to retrieve, e.g., 10, 20, null if not specified)
- scope_type: (type of scope: "top", "recent", "current", "latest", null if not specified)

SCOPE LOGIC:
- If user asks for "standings", "rankings", "leaderboard" → default to scope_limit: 10, scope_type: "top"
- If user says "top 20" or "top 10" → extract the number and set scope_limit
- If user says "current" or "latest" → set scope_type: "current", scope_limit: 10
- If user says "all" or doesn't specify → scope_limit: null, scope_type: null

Example outputs:
{{"intent": "search for current standings", "entities": ["standings", "rankings"], "tool_hint": "search", "user_input": "Find current standings", "scope_limit": 10, "scope_type": "top"}}
{{"intent": "find top 20 players", "entities": ["players", "rankings"], "tool_hint": "search", "user_input": "Find top 20 players", "scope_limit": 20, "scope_type": "top"}}
{{"intent": "get latest scores", "entities": ["scores", "results"], "tool_hint": "search", "user_input": "Get latest scores", "scope_limit": 10, "scope_type": "current"}}

OUTPUT ONLY THE JSON DICTIONARY, NOTHING ELSE.
"""

    try:
        response = await model.generate_text(prompt, max_retries=3, prompt_type="perception")

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
        parsed.setdefault("scope_limit", None)
        parsed.setdefault("scope_type", None)
        
        # Auto-detect scope for common queries
        if not parsed.get("scope_limit") and not parsed.get("scope_type"):
            user_lower = user_input.lower()
            # Check for explicit numbers (re is already imported at top)
            top_match = re.search(r'top\s+(\d+)', user_lower)
            if top_match:
                parsed["scope_limit"] = int(top_match.group(1))
                parsed["scope_type"] = "top"
            elif any(word in user_lower for word in ["standings", "rankings", "leaderboard", "points"]):
                # Default to top 10 for standings/rankings queries
                parsed["scope_limit"] = 10
                parsed["scope_type"] = "top"
            elif any(word in user_lower for word in ["current", "latest", "recent"]):
                parsed["scope_type"] = "current"
                parsed["scope_limit"] = 10
        
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
        
        # Ensure scope_limit is int or None
        if parsed.get("scope_limit") is not None:
            try:
                parsed["scope_limit"] = int(parsed["scope_limit"])
            except (ValueError, TypeError):
                parsed["scope_limit"] = None
        
        return PerceptionResult(**parsed)


    except Exception as e:
        print(f"[perception] ⚠️ LLM perception failed: {e}")
        # Return a valid PerceptionResult with all required fields
        return PerceptionResult(
            user_input=user_input,
            intent="process query",
            entities=[],
            tool_hint="search" if any(word in user_input.lower() for word in ["find", "search", "get", "show"]) else None,
            scope_limit=10 if any(word in user_input.lower() for word in ["standings", "rankings", "leaderboard", "points"]) else None,
            scope_type="top" if any(word in user_input.lower() for word in ["standings", "rankings", "leaderboard", "points"]) else None
        )
