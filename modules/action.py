# modules/action.py

from typing import Dict, Any, Union
from pydantic import BaseModel
import ast

# Optional logging fallback
try:
    from agent import log
except ImportError:
    import datetime
    def log(stage: str, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{stage}] {msg}")


class ToolCallResult(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result: Union[str, list, dict]
    raw_response: Any


def parse_function_call(response: str) -> tuple[str, Dict[str, Any]]:
    """
    Parses a FUNCTION_CALL string like:
    "FUNCTION_CALL: add|a=5|b=7"
    Into a tool name and a dictionary of arguments.
    """
    try:
        if not response.startswith("FUNCTION_CALL:"):
            raise ValueError("Invalid function call format.")

        _, raw = response.split(":", 1)
        parts = [p.strip() for p in raw.split("|")]
        tool_name, param_parts = parts[0], parts[1:]

        args = {}
        for part in param_parts:
            if "=" not in part:
                raise ValueError(f"Invalid parameter: {part}")
            
            # Handle the case where = appears in the value (e.g., in arrays with nested quotes)
            # Find the first = that's not inside quotes
            key = ""
            val = ""
            in_quotes = False
            quote_char = None
            split_pos = -1
            
            for i, char in enumerate(part):
                if char in ['"', "'"] and (i == 0 or part[i-1] != '\\'):
                    if not in_quotes:
                        in_quotes = True
                        quote_char = char
                    elif char == quote_char:
                        in_quotes = False
                        quote_char = None
                elif char == '=' and not in_quotes and split_pos == -1:
                    split_pos = i
                    key = part[:i].strip()
                    break
            
            if split_pos == -1:
                raise ValueError(f"Invalid parameter format (no = found): {part}")
            
            val = part[split_pos + 1:].strip()
            
            # Try parsing as literal, fallback to string
            parsed_val = None
            try:
                # First try ast.literal_eval (handles Python literals)
                parsed_val = ast.literal_eval(val)
            except (ValueError, SyntaxError):
                try:
                    # Try JSON parsing (handles JSON arrays/objects)
                    import json
                    parsed_val = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    # If both fail, treat as string but remove surrounding quotes if present
                    parsed_val = val.strip()
                    if len(parsed_val) >= 2 and parsed_val[0] == parsed_val[-1] and parsed_val[0] in ['"', "'"]:
                        parsed_val = parsed_val[1:-1]

            # Support nested keys (e.g., input.value)
            keys = key.split(".")
            current = args
            for k in keys[:-1]:
                current = current.setdefault(k, {})
            current[keys[-1]] = parsed_val
        
        # Special logging for add_data_to_sheet to debug data issues
        if tool_name == "add_data_to_sheet" and "input" in args:
            data = args["input"].get("data")
            log("parser", f"Parsed {tool_name}: data type={type(data)}, data length={len(data) if isinstance(data, list) else 'N/A'}")
            if isinstance(data, list) and len(data) > 0:
                log("parser", f"  First row: {data[0][:3] if len(data[0]) > 3 else data[0]}... ({len(data[0])} columns)")

        log("parser", f"Parsed: {tool_name} → {args}")
        return tool_name, args

    except Exception as e:
        log("parser", f"❌ Parse failed: {e}")
        log("parser", f"   Input was: {response[:200]}...")
        raise
