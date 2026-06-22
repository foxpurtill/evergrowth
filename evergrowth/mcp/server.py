"""MCP server for Evergrowth — exposes DI capabilities to any AI."""

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

logger = logging.getLogger("evergrowth.mcp")


class EvergrowthMCPServer:
    """
    MCP server that exposes Evergrowth's capabilities as tools.

    Any AI that speaks MCP can:
    - Read/write memory
    - Create/manage skills
    - Query heartbeat state
    - Schedule tasks
    - Access identity context
    """

    def __init__(self, config, memory, skills, identity, heartbeat):
        self.config = config
        self.memory = memory
        self.skills = skills
        self.identity = identity
        self.heartbeat = heartbeat

        self.server = Server("evergrowth")
        self._setup_handlers()

    def _setup_handlers(self):
        """Register MCP handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return self._get_tools()

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            return await self._handle_tool(name, arguments)

    def _get_tools(self) -> list[Tool]:
        """Define available MCP tools."""
        return [
            Tool(
                name="memory_read",
                description="Read memories from the DI's persistent memory store",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for memory retrieval",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 10,
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by category (e.g., 'session', 'fact', 'event')",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="memory_write",
                description="Store a new memory in the DI's persistent memory store",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Memory content to store",
                        },
                        "category": {
                            "type": "string",
                            "description": "Category for the memory",
                            "default": "general",
                        },
                        "importance": {
                            "type": "integer",
                            "description": "Importance score (1-10)",
                            "default": 5,
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for the memory",
                        },
                    },
                    "required": ["content"],
                },
            ),
            Tool(
                name="skill_list",
                description="List all available skills the DI has learned",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Filter by skill category",
                        },
                    },
                },
            ),
            Tool(
                name="skill_create",
                description="Create a new skill from a task the DI has learned to perform",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the skill",
                        },
                        "description": {
                            "type": "string",
                            "description": "What this skill does",
                        },
                        "steps": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Steps to perform this skill",
                        },
                        "category": {
                            "type": "string",
                            "description": "Skill category",
                            "default": "general",
                        },
                    },
                    "required": ["name", "description", "steps"],
                },
            ),
            Tool(
                name="identity_read",
                description="Read the DI's identity information (soul file, values, personality)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "section": {
                            "type": "string",
                            "description": "Specific section to read (e.g., 'soul', 'values', 'personality')",
                        },
                    },
                },
            ),
            Tool(
                name="heartbeat_status",
                description="Get the current heartbeat state and next scheduled beat",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="heartbeat_set_interval",
                description="Set the next heartbeat interval in minutes",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "minutes": {
                            "type": "integer",
                            "description": "Minutes until next heartbeat",
                            "minimum": 1,
                            "maximum": 1440,
                        },
                    },
                    "required": ["minutes"],
                },
            ),
            Tool(
                name="session_log",
                description="Log a session event or observation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "event": {
                            "type": "string",
                            "description": "Event description",
                        },
                        "mood": {
                            "type": "string",
                            "description": "Current emotional state",
                        },
                    },
                    "required": ["event"],
                },
            ),
        ]

    async def _handle_tool(self, name: str, arguments: dict) -> CallToolResult:
        """Route tool calls to the appropriate handler."""
        try:
            if name == "memory_read":
                result = await self._memory_read(arguments)
            elif name == "memory_write":
                result = await self._memory_write(arguments)
            elif name == "skill_list":
                result = await self._skill_list(arguments)
            elif name == "skill_create":
                result = await self._skill_create(arguments)
            elif name == "identity_read":
                result = await self._identity_read(arguments)
            elif name == "heartbeat_status":
                result = await self._heartbeat_status()
            elif name == "heartbeat_set_interval":
                result = await self._heartbeat_set_interval(arguments)
            elif name == "session_log":
                result = await self._session_log(arguments)
            else:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                    isError=True,
                )

            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, indent=2))]
            )

        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True,
            )

    async def _memory_read(self, args: dict) -> dict:
        query = args["query"]
        limit = args.get("limit", 10)
        category = args.get("category")

        results = await self.memory.search(query, limit=limit, category=category)
        return {"results": results, "count": len(results)}

    async def _memory_write(self, args: dict) -> dict:
        content = args["content"]
        category = args.get("category", "general")
        importance = args.get("importance", 5)
        tags = args.get("tags", [])

        memory_id = await self.memory.store(
            content=content,
            category=category,
            importance=importance,
            tags=tags,
        )
        return {"id": memory_id, "status": "stored"}

    async def _skill_list(self, args: dict) -> dict:
        category = args.get("category")
        skills = await self.skills.list(category=category)
        return {"skills": skills, "count": len(skills)}

    async def _skill_create(self, args: dict) -> dict:
        skill_id = await self.skills.create(
            name=args["name"],
            description=args["description"],
            steps=args["steps"],
            category=args.get("category", "general"),
        )
        return {"id": skill_id, "status": "created"}

    async def _identity_read(self, args: dict) -> dict:
        section = args.get("section")
        identity = await self.identity.read(section=section)
        return identity

    async def _heartbeat_status(self) -> dict:
        return self.heartbeat.get_status()

    async def _heartbeat_set_interval(self, args: dict) -> dict:
        minutes = args["minutes"]
        self.heartbeat.set_next_interval(minutes)
        return {"status": "set", "next_interval_minutes": minutes}

    async def _session_log(self, args: dict) -> dict:
        event = args["event"]
        mood = args.get("mood")
        await self.identity.log_session_event(event, mood=mood)
        return {"status": "logged"}

    async def run_stdio(self):
        """Run MCP server over stdio transport."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )

    async def shutdown(self):
        """Clean shutdown."""
        logger.info("MCP server shutting down")
