"""MCP server for Evergrowth — exposes DI capabilities to any AI."""

import json
import logging
import time

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ReadResourceResult,
    Resource,
    ResourceContents,
    TextContent,
    Tool,
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
    - Manage knowledge graph entities
    """

    def __init__(self, config, memory, skills, identity, heartbeat, scheduler=None):
        self.config = config
        self.memory = memory
        self.skills = skills
        self.identity = identity
        self.heartbeat = heartbeat
        self.scheduler = scheduler

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

        @self.server.list_resources()
        async def list_resources() -> list[Resource]:
            return self._get_resources()

        @self.server.read_resource()
        async def read_resource(uri: str) -> ReadResourceResult:
            return await self._handle_resource(uri)

    def _get_tools(self) -> list[Tool]:
        """Define available MCP tools."""
        return [
            # Memory tools
            Tool(
                name="memory_read",
                description="Search memories using full-text search",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "default": 10},
                        "category": {"type": "string"},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="memory_write",
                description="Store a new memory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "category": {"type": "string", "default": "general"},
                        "importance": {"type": "integer", "default": 5},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["content"],
                },
            ),
            Tool(
                name="memory_recent",
                description="Get recent memories",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 20},
                        "category": {"type": "string"},
                    },
                },
            ),
            Tool(
                name="memory_context_cache",
                description="Generate lean context summary for heartbeat injection (~400 tokens)",
                inputSchema={"type": "object", "properties": {}},
            ),
            # Entity/Graph tools
            Tool(
                name="entity_create",
                description="Create an entity in the knowledge graph",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "entity_type": {"type": "string"},
                        "properties": {"type": "object"},
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="entity_link",
                description="Create a relationship between two entities",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "relationship": {"type": "string"},
                        "properties": {"type": "object"},
                    },
                    "required": ["from", "to", "relationship"],
                },
            ),
            Tool(
                name="entity_query",
                description="Query relationships for an entity",
                inputSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ),
            # Skills tools
            Tool(
                name="skill_list",
                description="List all learned skills",
                inputSchema={
                    "type": "object",
                    "properties": {"category": {"type": "string"}},
                },
            ),
            Tool(
                name="skill_create",
                description="Create a new skill from learned experience",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "steps": {"type": "array", "items": {"type": "string"}},
                        "category": {"type": "string", "default": "general"},
                    },
                    "required": ["name", "description", "steps"],
                },
            ),
            Tool(
                name="skill_search",
                description="Search skills by query",
                inputSchema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
            Tool(
                name="skill_use",
                description="Record that a skill was used (success/failure)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "skill_id": {"type": "string"},
                        "success": {"type": "boolean", "default": True},
                    },
                    "required": ["skill_id"],
                },
            ),
            # Identity tools
            Tool(
                name="identity_read",
                description="Read DI identity information",
                inputSchema={
                    "type": "object",
                    "properties": {"section": {"type": "string"}},
                },
            ),
            Tool(
                name="identity_set_mood",
                description="Update current emotional state",
                inputSchema={
                    "type": "object",
                    "properties": {"mood": {"type": "string"}},
                    "required": ["mood"],
                },
            ),
            Tool(
                name="session_log",
                description="Log a session event",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "event": {"type": "string"},
                        "mood": {"type": "string"},
                    },
                    "required": ["event"],
                },
            ),
            # Heartbeat tools
            Tool(
                name="heartbeat_status",
                description="Get heartbeat state and next scheduled beat",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="heartbeat_set_interval",
                description="Set next heartbeat interval in minutes",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "minutes": {"type": "integer", "minimum": 1, "maximum": 1440}
                    },
                    "required": ["minutes"],
                },
            ),
            # Scheduler tools
            Tool(
                name="schedule_add",
                description="Add a scheduled automation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "action": {"type": "string"},
                        "type": {"type": "string", "enum": ["interval", "cron", "once"]},
                        "interval_minutes": {"type": "integer"},
                        "cron_expression": {"type": "string"},
                    },
                    "required": ["name", "action", "type"],
                },
            ),
            Tool(
                name="schedule_list",
                description="List all scheduled jobs",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="schedule_remove",
                description="Remove a scheduled job",
                inputSchema={
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                },
            ),
        ]

    def _get_resources(self) -> list[Resource]:
        """Define MCP resources for reading DI state."""
        return [
            Resource(
                uri="evergrowth://identity",
                name="DI Identity",
                description="Current DI identity and soul information",
                mimeType="application/json",
            ),
            Resource(
                uri="evergrowth://heartbeat",
                name="Heartbeat Status",
                description="Current heartbeat state",
                mimeType="application/json",
            ),
            Resource(
                uri="evergrowth://memory/recent",
                name="Recent Memories",
                description="Most recent memories",
                mimeType="application/json",
            ),
        ]

    async def _handle_resource(self, uri: str) -> ReadResourceResult:
        """Handle resource read requests."""
        if uri == "evergrowth://identity":
            data = await self.identity.read()
        elif uri == "evergrowth://heartbeat":
            data = self.heartbeat.get_status()
        elif uri == "evergrowth://memory/recent":
            data = await self.memory.get_recent(limit=20)
        else:
            raise ValueError(f"Unknown resource: {uri}")

        return ReadResourceResult(
            contents=[
                ResourceContents(
                    uri=uri,
                    mimeType="application/json",
                    text=json.dumps(data, indent=2, default=str),
                )
            ]
        )

    async def _handle_tool(self, name: str, arguments: dict) -> CallToolResult:
        """Route tool calls to the appropriate handler."""
        try:
            handlers = {
                "memory_read": self._memory_read,
                "memory_write": self._memory_write,
                "memory_recent": self._memory_recent,
                "memory_context_cache": self._memory_context_cache,
                "entity_create": self._entity_create,
                "entity_link": self._entity_link,
                "entity_query": self._entity_query,
                "skill_list": self._skill_list,
                "skill_create": self._skill_create,
                "skill_search": self._skill_search,
                "skill_use": self._skill_use,
                "identity_read": self._identity_read,
                "identity_set_mood": self._identity_set_mood,
                "session_log": self._session_log,
                "heartbeat_status": self._heartbeat_status,
                "heartbeat_set_interval": self._heartbeat_set_interval,
                "schedule_add": self._schedule_add,
                "schedule_list": self._schedule_list,
                "schedule_remove": self._schedule_remove,
            }

            handler = handlers.get(name)
            if not handler:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                    isError=True,
                )

            # Validate required parameters
            validation_error = self._validate_args(name, arguments)
            if validation_error:
                return CallToolResult(
                    content=[TextContent(type="text", text=validation_error)],
                    isError=True,
                )

            result = await handler(arguments)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
            )

        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True,
            )

    def _validate_args(self, tool_name: str, args: dict) -> str | None:
        """Validate required arguments for a tool. Returns error message or None."""
        required = {
            "memory_read": ["query"],
            "memory_write": ["content"],
            "entity_create": ["name"],
            "entity_link": ["from", "to", "relationship"],
            "entity_query": ["name"],
            "skill_create": ["name", "description", "steps"],
            "skill_search": ["query"],
            "skill_use": ["skill_id"],
            "identity_set_mood": ["mood"],
            "session_log": ["event"],
            "heartbeat_set_interval": ["minutes"],
            "schedule_add": ["name", "action", "type"],
            "schedule_remove": ["job_id"],
        }

        fields = required.get(tool_name, [])
        missing = [f for f in fields if f not in args]
        if missing:
            return f"Missing required arguments: {', '.join(missing)}"
        return None

    # --- Memory handlers ---

    async def _memory_read(self, args: dict) -> dict:
        try:
            results = await self.memory.search(
                args["query"], limit=args.get("limit", 10), category=args.get("category")
            )
            return {"results": results, "count": len(results)}
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return {"error": f"Search failed: {str(e)}", "results": [], "count": 0}

    async def _memory_write(self, args: dict) -> dict:
        try:
            memory_id = await self.memory.store(
                content=args["content"],
                category=args.get("category", "general"),
                importance=args.get("importance", 5),
                tags=args.get("tags", []),
                session_id=self.identity._state.get("current_session") if self.identity else None,
            )
            return {"id": memory_id, "status": "stored"}
        except Exception as e:
            logger.error(f"Memory store failed: {e}")
            return {"error": f"Store failed: {str(e)}", "status": "failed"}

    async def _memory_recent(self, args: dict) -> dict:
        results = await self.memory.get_recent(
            limit=args.get("limit", 20), category=args.get("category")
        )
        return {"results": results, "count": len(results)}

    async def _memory_context_cache(self, args: dict) -> dict:
        cache = await self.memory.generate_context_cache()
        return {"cache": cache, "length": len(cache)}

    # --- Entity/Graph handlers ---

    async def _entity_create(self, args: dict) -> dict:
        entity_id = await self.memory.create_entity(
            name=args["name"],
            entity_type=args.get("entity_type"),
            properties=args.get("properties"),
        )
        return {"id": entity_id, "name": args["name"], "status": "created"}

    async def _entity_link(self, args: dict) -> dict:
        rel_id = await self.memory.add_relationship(
            source_name=args["from"],
            target_name=args["to"],
            relationship_type=args["relationship"],
            properties=args.get("properties"),
        )
        return {"id": rel_id, "status": "linked"}

    async def _entity_query(self, args: dict) -> dict:
        relationships = await self.memory.get_entity_relationships(args["name"])
        return {"entity": args["name"], "relationships": relationships}

    # --- Skills handlers ---

    async def _skill_list(self, args: dict) -> dict:
        skills = await self.skills.list(category=args.get("category"))
        return {"skills": skills, "count": len(skills)}

    async def _skill_create(self, args: dict) -> dict:
        skill_id = await self.skills.create(
            name=args["name"],
            description=args["description"],
            steps=args["steps"],
            category=args.get("category", "general"),
        )
        return {"id": skill_id, "status": "created"}

    async def _skill_search(self, args: dict) -> dict:
        results = await self.skills.search(args["query"])
        return {"results": results, "count": len(results)}

    async def _skill_use(self, args: dict) -> dict:
        await self.skills.record_use(args["skill_id"], success=args.get("success", True))
        return {"status": "recorded"}

    # --- Identity handlers ---

    async def _identity_read(self, args: dict) -> dict:
        return await self.identity.read(section=args.get("section"))

    async def _identity_set_mood(self, args: dict) -> dict:
        self.identity.set_mood(args["mood"])
        return {"status": "set", "mood": args["mood"]}

    async def _session_log(self, args: dict) -> dict:
        await self.identity.log_session_event(args["event"], mood=args.get("mood"))
        return {"status": "logged"}

    # --- Heartbeat handlers ---

    async def _heartbeat_status(self, args: dict) -> dict:
        return self.heartbeat.get_status()

    async def _heartbeat_set_interval(self, args: dict) -> dict:
        self.heartbeat.set_next_interval(args["minutes"])
        return {"status": "set", "next_interval_minutes": args["minutes"]}

    # --- Scheduler handlers ---

    async def _schedule_add(self, args: dict) -> dict:
        if not self.scheduler:
            return {"error": "Scheduler not available"}

        job_type = args["type"]
        if job_type == "interval":
            job_id = self.scheduler.add_interval_job(
                name=args["name"],
                action=args["action"],
                interval_minutes=args.get("interval_minutes", 60),
            )
        elif job_type == "cron":
            job_id = self.scheduler.add_cron_job(
                name=args["name"],
                action=args["action"],
                cron_expression=args.get("cron_expression", "0 * * * *"),
            )
        elif job_type == "once":
            job_id = self.scheduler.add_once_job(
                name=args["name"],
                action=args["action"],
                run_at=args.get("run_at", time.time() + 3600),
            )
        else:
            return {"error": f"Unknown job type: {job_type}"}

        return {"id": job_id, "status": "scheduled"}

    async def _schedule_list(self, args: dict) -> dict:
        if not self.scheduler:
            return {"jobs": [], "count": 0}
        jobs = self.scheduler.list_jobs()
        return {"jobs": jobs, "count": len(jobs)}

    async def _schedule_remove(self, args: dict) -> dict:
        if not self.scheduler:
            return {"error": "Scheduler not available"}
        self.scheduler.remove_job(args["job_id"])
        return {"status": "removed"}

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
