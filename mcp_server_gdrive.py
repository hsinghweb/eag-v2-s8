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
        sheets_service = build('sheets', 'v4', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        print("✅ Google Sheets/Drive services initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Google services: {e}")
        sys.exit(1)


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Tool Implementations
async def create_google_sheet(args: Dict[str, Any]) -> Dict[str, str]:
    """Create a new Google Spreadsheet"""
    try:
        title = args.get("title") or args.get("input", {}).get("title", "Untitled Spreadsheet")
        
        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        
        spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId,spreadsheetUrl').execute()
        
        sheet_id = spreadsheet.get('spreadsheetId')
        sheet_url = spreadsheet.get('spreadsheetUrl')
        
        return {
            "sheet_id": sheet_id,
            "sheet_url": sheet_url
        }
    except HttpError as error:
        raise Exception(f"Google Sheets API error: {error}")
    except Exception as e:
        raise Exception(f"Failed to create sheet: {e}")


async def add_data_to_sheet(args: Dict[str, Any]) -> Dict[str, str]:
    """Add data to a Google Sheet"""
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
        
        if not sheet_id or not data:
            raise ValueError("sheet_id and data are required")
        
        body = {
            'values': data
        }
        
        result = sheets_service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()
        
        return {
            "updated_cells": result.get('updatedCells', 0),
            "updated_range": result.get('updatedRange', ''),
            "success": True
        }
    except HttpError as error:
        raise Exception(f"Google Sheets API error: {error}")
    except Exception as e:
        raise Exception(f"Failed to add data: {e}")


async def get_sheet_link(args: Dict[str, Any]) -> Dict[str, str]:
    """Get shareable link for a Google Sheet"""
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

