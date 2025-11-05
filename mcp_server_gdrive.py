"""
MCP Server for Google Sheets/Drive (SSE Transport)
Provides tools to create spreadsheets, add data, and share files.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
import json
import os
from dotenv import load_dotenv
import sys

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from models import (
    CreateSheetInput, CreateSheetOutput,
    AddDataInput, ShareSheetInput,
    SheetLinkInput, SheetLinkOutput
)

load_dotenv()

# Google API Scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

app = FastAPI(title="Google Sheets/Drive MCP Server")

# Global service objects (initialized on startup)
sheets_service = None
drive_service = None


class ToolCallRequest(BaseModel):
    method: str
    params: Dict[str, Any]


class ToolCallResponse(BaseModel):
    result: Any


def get_google_credentials():
    """Get or refresh Google API credentials"""
    creds = None
    token_file = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
    credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    
    # Load existing token
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"Credentials file not found: {credentials_file}\n"
                    "Please download OAuth2 credentials from Google Cloud Console"
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
    
    return creds


@app.on_event("startup")
async def startup():
    """Initialize Google API services"""
    global sheets_service, drive_service
    try:
        creds = get_google_credentials()
        if creds:
            sheets_service = build('sheets', 'v4', credentials=creds)
            drive_service = build('drive', 'v3', credentials=creds)
            print("✅ Google Sheets/Drive services initialized", file=sys.stderr)
        else:
            print("⚠️ No credentials available on startup. Services will be initialized on first tool call.", file=sys.stderr)
    except Exception as e:
        print(f"⚠️ Failed to initialize Google services: {e}", file=sys.stderr)
        print("⚠️ Services will be initialized on first tool call", file=sys.stderr)


# MCP Protocol Endpoints
@app.get("/mcp/tools")
async def list_tools():
    """List available tools (MCP protocol)"""
    tools = [
        {
            "name": "create_google_sheet",
            "description": "Create a new Google Spreadsheet. Usage: create_google_sheet|input.title=\"F1 Standings\"",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the spreadsheet"}
                },
                "required": ["title"]
            }
        },
        {
            "name": "add_data_to_sheet",
            "description": "Add data to a Google Sheet. Usage: add_data_to_sheet|input.sheet_id=\"...\"|input.data=[[\"Header1\",\"Header2\"],[\"Row1Col1\",\"Row1Col2\"]]|input.range=\"A1\"",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_id": {"type": "string"},
                    "data": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                    "range": {"type": "string", "default": "A1"}
                },
                "required": ["sheet_id", "data"]
            }
        },
        {
            "name": "get_sheet_link",
            "description": "Get shareable link for a Google Sheet. Usage: get_sheet_link|input.sheet_id=\"...\"",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_id": {"type": "string"}
                },
                "required": ["sheet_id"]
            }
        },
        {
            "name": "share_sheet",
            "description": "Share a Google Sheet with an email. Usage: share_sheet|input.sheet_id=\"...\"|input.email=\"user@example.com\"|input.role=\"writer\"",
            "parameters": {
                "type": "object",
                "properties": {
                    "sheet_id": {"type": "string"},
                    "email": {"type": "string"},
                    "role": {"type": "string", "default": "writer"}
                },
                "required": ["sheet_id", "email"]
            }
        }
    ]
    return {"tools": tools}


@app.post("/mcp/call_tool")
async def call_tool(request: ToolCallRequest):
    """Execute a tool call (MCP protocol)"""
    try:
        tool_name = request.params.get("name")
        arguments = request.params.get("arguments", {})
        
        if tool_name == "create_google_sheet":
            result = await create_google_sheet(arguments)
        elif tool_name == "add_data_to_sheet":
            result = await add_data_to_sheet(arguments)
        elif tool_name == "get_sheet_link":
            result = await get_sheet_link(arguments)
        elif tool_name == "share_sheet":
            result = await share_sheet(arguments)
        else:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
        
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Tool execution error: {error_msg}", file=sys.stderr)
        raise HTTPException(status_code=500, detail=error_msg)


# Tool Implementations
async def create_google_sheet(args: Dict[str, Any]) -> Dict[str, str]:
    """Create a new Google Spreadsheet"""
    global sheets_service, drive_service
    
    # Ensure services are initialized
    if sheets_service is None or drive_service is None:
        try:
            creds = get_google_credentials()
            sheets_service = build('sheets', 'v4', credentials=creds)
            drive_service = build('drive', 'v3', credentials=creds)
        except Exception as e:
            raise Exception(f"Failed to initialize Google services: {e}")
    
    try:
        # Handle nested input structure
        if "input" in args and isinstance(args["input"], dict):
            title = args["input"].get("title", "Untitled Spreadsheet")
        else:
            title = args.get("title", "Untitled Spreadsheet")
        
        if not title:
            title = "Untitled Spreadsheet"
        
        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        
        spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId,spreadsheetUrl').execute()
        
        sheet_id = spreadsheet.get('spreadsheetId')
        sheet_url = spreadsheet.get('spreadsheetUrl')
        
        if not sheet_id:
            raise Exception("Failed to get sheet_id from Google Sheets API response")
        
        return {
            "sheet_id": sheet_id,
            "sheet_url": sheet_url or f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        }
    except HttpError as error:
        raise Exception(f"Google Sheets API error: {error}")
    except Exception as e:
        raise Exception(f"Failed to create sheet: {e}")


async def add_data_to_sheet(args: Dict[str, Any]) -> Dict[str, str]:
    """Add data to a Google Sheet"""
    global sheets_service
    
    # Ensure services are initialized
    if sheets_service is None:
        try:
            creds = get_google_credentials()
            sheets_service = build('sheets', 'v4', credentials=creds)
        except Exception as e:
            raise Exception(f"Failed to initialize Google Sheets service: {e}")
    
    try:
        # Handle both direct args and nested input
        if "input" in args:
            sheet_id = args["input"].get("sheet_id")
            data = args["input"].get("data")
            range_name = args["input"].get("range", "A1")
        else:
            sheet_id = args.get("sheet_id")
            data = args.get("data")
            range_name = args.get("range", "A1")
        
        # Log received arguments for debugging
        print(f"[add_data_to_sheet] Received args: sheet_id={sheet_id}, data_type={type(data)}, range={range_name}", file=sys.stderr)
        if data:
            print(f"[add_data_to_sheet] Data preview: {str(data)[:200]}...", file=sys.stderr)
        
        if not sheet_id:
            raise ValueError("sheet_id is required")
        
        # Validate sheet_id format (Google Sheet IDs are alphanumeric, typically 44 characters)
        if not isinstance(sheet_id, str):
            sheet_id = str(sheet_id)
        
        # Google Sheet IDs are typically long alphanumeric strings
        # If it's just a number (like 611513920), it's likely wrong
        if sheet_id.isdigit() and len(sheet_id) < 20:
            raise ValueError(f"Invalid sheet_id format: '{sheet_id}' appears to be a number, not a valid Google Sheet ID. Sheet IDs are typically long alphanumeric strings (44+ characters).")
        
        # Basic validation - should contain alphanumeric characters
        if not any(c.isalnum() for c in sheet_id):
            raise ValueError(f"Invalid sheet_id format: '{sheet_id}' does not appear to be a valid Google Sheet ID.")
        
        if not data:
            raise ValueError("data is required")
        
        # Try to parse data if it's a string (might happen if LLM passes it as string)
        if isinstance(data, str):
            print(f"[add_data_to_sheet] ⚠️ Data is a string, attempting to parse...", file=sys.stderr)
            try:
                import json
                data = json.loads(data)
                print(f"[add_data_to_sheet] ✅ Successfully parsed data from string", file=sys.stderr)
            except json.JSONDecodeError:
                try:
                    import ast
                    data = ast.literal_eval(data)
                    print(f"[add_data_to_sheet] ✅ Successfully parsed data using ast.literal_eval", file=sys.stderr)
                except Exception as parse_error:
                    raise ValueError(f"data is a string but could not be parsed as JSON or Python literal: {parse_error}. Data: {data[:100]}")
        
        # Validate data format - must be a list of lists
        if not isinstance(data, list):
            raise ValueError(f"data must be a list (2D array), got {type(data)}: {data}")
        if len(data) == 0:
            raise ValueError("data cannot be empty - the list must contain at least one row (even if just headers)")
        if not isinstance(data[0], list):
            raise ValueError(f"data must be a 2D array (list of lists), first element is {type(data[0])}: {data[0]}")
        
        # Validate all rows are lists
        for i, row in enumerate(data):
            if not isinstance(row, list):
                raise ValueError(f"Row {i} is not a list: {type(row)}: {row}")
            # Convert all values to strings (Google Sheets API expects strings or numbers)
            data[i] = [str(cell) if cell is not None else "" for cell in row]
        
        print(f"[add_data_to_sheet] ✅ Data validated: {len(data)} rows, {len(data[0]) if data else 0} columns", file=sys.stderr)
        
        body = {
            'values': data
        }
        
        result = sheets_service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()
        
        updated_cells = result.get('updatedCells', 0)
        updated_range = result.get('updatedRange', '')
        
        print(f"[add_data_to_sheet] ✅ Successfully updated {updated_cells} cells in range {updated_range}", file=sys.stderr)
        
        return {
            "updated_cells": updated_cells,
            "updated_range": updated_range,
            "success": True,
            "rows_added": len(data),
            "columns_added": len(data[0]) if data else 0
        }
    except HttpError as error:
        error_details = f"Google Sheets API error: {error}"
        print(f"[add_data_to_sheet] ❌ {error_details}", file=sys.stderr)
        raise Exception(error_details)
    except Exception as e:
        error_details = f"Failed to add data: {e}"
        print(f"[add_data_to_sheet] ❌ {error_details}", file=sys.stderr)
        import traceback
        print(f"[add_data_to_sheet] Traceback: {traceback.format_exc()}", file=sys.stderr)
        raise Exception(error_details)


async def get_sheet_link(args: Dict[str, Any]) -> Dict[str, str]:
    """Get shareable link for a Google Sheet"""
    global drive_service
    
    # Ensure services are initialized
    if drive_service is None:
        try:
            creds = get_google_credentials()
            drive_service = build('drive', 'v3', credentials=creds)
        except Exception as e:
            raise Exception(f"Failed to initialize Google Drive service: {e}")
    
    try:
        if "input" in args:
            sheet_id = args["input"].get("sheet_id")
        else:
            sheet_id = args.get("sheet_id")
        
        if not sheet_id:
            raise ValueError("sheet_id is required")
        
        # Get file metadata to construct URL
        file_metadata = drive_service.files().get(fileId=sheet_id, fields='webViewLink').execute()
        link = file_metadata.get('webViewLink', f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
        
        return {"link": link}
    except HttpError as error:
        raise Exception(f"Google Drive API error: {error}")
    except Exception as e:
        raise Exception(f"Failed to get sheet link: {e}")


async def share_sheet(args: Dict[str, Any]) -> Dict[str, str]:
    """Share a Google Sheet with an email"""
    global drive_service
    
    # Ensure services are initialized
    if drive_service is None:
        try:
            creds = get_google_credentials()
            drive_service = build('drive', 'v3', credentials=creds)
        except Exception as e:
            raise Exception(f"Failed to initialize Google Drive service: {e}")
    
    try:
        if "input" in args:
            sheet_id = args["input"].get("sheet_id")
            email = args["input"].get("email")
            role = args["input"].get("role", "writer")
        else:
            sheet_id = args.get("sheet_id")
            email = args.get("email")
            role = args.get("role", "writer")
        
        if not sheet_id or not email:
            raise ValueError("sheet_id and email are required")
        
        permission = {
            'type': 'user',
            'role': role,
            'emailAddress': email
        }
        
        drive_service.permissions().create(
            fileId=sheet_id,
            body=permission
        ).execute()
        
        return {"success": True, "message": f"Shared with {email} as {role}"}
    except HttpError as error:
        raise Exception(f"Google Drive API error: {error}")
    except Exception as e:
        raise Exception(f"Failed to share sheet: {e}")


if __name__ == "__main__":
    port = int(os.getenv("GDRIVE_SERVER_PORT", "8002"))
    print(f"🚀 Starting Google Sheets/Drive MCP Server (SSE) on port {port}")
    print(f"📋 MCP endpoint: http://localhost:{port}/mcp/tools")
    uvicorn.run(app, host="0.0.0.0", port=port)

