# core/session.py

import os
import sys
import json
from typing import Optional, Any, List, Dict
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import httpx
from dataclasses import dataclass


@dataclass
class SSEServerParameters:
    """Parameters for SSE (HTTP) transport MCP servers"""
    base_url: str
    api_key: Optional[str] = None
    timeout: float = 30.0


class SSEClient:
    """Client for SSE-based MCP servers"""
    
    def __init__(self, params: SSEServerParameters):
        self.params = params
        self.client = httpx.AsyncClient(timeout=params.timeout)
        self.headers = {"Content-Type": "application/json"}
        if params.api_key:
            self.headers["Authorization"] = f"Bearer {params.api_key}"
    
    async def list_tools(self):
        """List tools from SSE MCP server"""
        try:
            url = f"{self.params.base_url}/mcp/tools"
            response = await self.client.get(url, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            # Return tools in format compatible with MCP
            class ToolWrapper:
                def __init__(self, tool_dict):
                    for k, v in tool_dict.items():
                        setattr(self, k, v)
            
            class ToolsResult:
                def __init__(self, tools_list):
                    self.tools = [ToolWrapper(t) for t in tools_list]
            
            return ToolsResult(result.get("tools", []))
        except Exception as e:
            print(f"❌ SSE list_tools error: {e}")
            class ToolsResult:
                def __init__(self):
                    self.tools = []
            return ToolsResult()
    
    async def call_tool(self, tool_name: str, arguments: dict):
        """Call a tool on SSE MCP server"""
        try:
            url = f"{self.params.base_url}/mcp/call_tool"
            payload = {
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            response = await self.client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            
            # Parse response - SSE servers return JSON directly
            result = response.json()
            
            # Extract the actual result from the response
            tool_result = result.get("result")
            if tool_result is None:
                tool_result = result
            
            # Return in format compatible with MCP TextContent
            class TextContent:
                def __init__(self, text):
                    self.text = text if text is not None else ""
                    self.type = "text"
            
            class ToolResult:
                def __init__(self, content):
                    if content is None:
                        self.content = TextContent("")
                    elif isinstance(content, dict):
                        # Return as JSON string for consistent parsing
                        self.content = TextContent(json.dumps(content))
                    else:
                        self.content = TextContent(str(content))
            
            return ToolResult(tool_result)
        except Exception as e:
            print(f"❌ SSE call_tool error: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


class MCP:
    """
    Lightweight wrapper for one-time MCP tool calls using stdio transport.
    Each call spins up a new subprocess and terminates cleanly.
    """

    def __init__(
        self,
        server_script: str = "mcp_server_2.py",
        working_dir: Optional[str] = None,
        server_command: Optional[str] = None,
    ):
        self.server_script = server_script
        self.working_dir = working_dir or os.getcwd()
        self.server_command = server_command or sys.executable

    async def list_tools(self):
        server_params = StdioServerParameters(
            command=self.server_command,
            args=[self.server_script],
            cwd=self.working_dir
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                return tools_result.tools

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        server_params = StdioServerParameters(
            command=self.server_command,
            args=[self.server_script],
            cwd=self.working_dir
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool_name, arguments=arguments)


class MultiMCP:
    """
    Stateless version: discovers tools from multiple MCP servers, but reconnects per tool call.
    Each call_tool() uses a fresh session based on tool-to-server mapping.
    """

    def __init__(self, server_configs: List[dict]):
        self.server_configs = server_configs
        self.tool_map: Dict[str, Dict[str, Any]] = {}  # tool_name → {config, tool}

    async def initialize(self):
        print("in MultiMCP initialize")
        for config in self.server_configs:
            try:
                transport = config.get("transport", "stdio")
                
                if transport == "sse":
                    # SSE transport
                    base_url = config.get("base_url")
                    if not base_url:
                        print(f"❌ SSE server missing base_url in config")
                        continue
                    
                    print(f"→ Scanning SSE tools from: {base_url}")
                    params = SSEServerParameters(
                        base_url=base_url,
                        api_key=config.get("api_key")
                    )
                    sse_client = SSEClient(params)
                    
                    try:
                        tools_result = await sse_client.list_tools()
                        print(f"→ Tools received: {[tool.name for tool in tools_result.tools]}")
                        for tool in tools_result.tools:
                            self.tool_map[tool.name] = {
                                "config": config,
                                "tool": tool,
                                "transport": "sse",
                                "sse_client_class": SSEClient,
                                "sse_params": params
                            }
                        await sse_client.close()
                    except Exception as se:
                        print(f"❌ SSE initialization error: {se}")
                
                else:
                    # Stdio transport (default)
                    params = StdioServerParameters(
                        command=sys.executable,
                        args=[config["script"]],
                        cwd=config.get("cwd", os.getcwd())
                    )
                    print(f"→ Scanning tools from: {config['script']} in {params.cwd}")
                    async with stdio_client(params) as (read, write):
                        print("Connection established, creating session...")
                        try:
                            async with ClientSession(read, write) as session:
                                print("[agent] Session created, initializing...")
                                await session.initialize()
                                print("[agent] MCP session initialized")
                                tools = await session.list_tools()
                                print(f"→ Tools received: {[tool.name for tool in tools.tools]}")
                                for tool in tools.tools:
                                    self.tool_map[tool.name] = {
                                        "config": config,
                                        "tool": tool,
                                        "transport": "stdio"
                                    }
                        except Exception as se:
                            print(f"❌ Session error: {se}")
            except Exception as e:
                print(f"❌ Error initializing MCP server: {e}")

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        entry = self.tool_map.get(tool_name)
        if not entry:
            raise ValueError(f"Tool '{tool_name}' not found on any server.")

        transport = entry.get("transport", "stdio")
        
        if transport == "sse":
            # SSE transport
            sse_client = SSEClient(entry["sse_params"])
            try:
                result = await sse_client.call_tool(tool_name, arguments)
                return result
            finally:
                await sse_client.close()
        else:
            # Stdio transport
            config = entry["config"]
            params = StdioServerParameters(
                command=sys.executable,
                args=[config["script"]],
                cwd=config.get("cwd", os.getcwd())
            )

            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(tool_name, arguments)

    async def list_all_tools(self) -> List[str]:
        return list(self.tool_map.keys())

    def get_all_tools(self) -> List[Any]:
        return [entry["tool"] for entry in self.tool_map.values()]

    async def shutdown(self):
        pass  # no persistent sessions to close