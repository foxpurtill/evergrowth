"""Persistent memory engine for Evergrowth — SQLite with FTS5 search."""

import json
import logging
import time
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger("evergrowth.memory")


class MemoryEngine:
    """
    Persistent memory store using SQLite with FTS5 full-text search.

    Memory is organized by:
    - Category (session, fact, event, emotion, observation)
    - Importance (1-10)
    - Tags (flexible labeling)
    - Timestamps (when things happened)
    """

    def __init__(self, config):
        self.config = config
        self.db_path = config.resolve_memory_path()
        self.db: aiosqlite.Connection | None = None

    async def initialize(self):
        """Create database and tables if they don't exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(str(self.db_path))

        # Enable WAL mode for better concurrent access
        await self.db.execute("PRAGMA journal_mode=WAL")

        # Create main memories table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                importance INTEGER NOT NULL DEFAULT 5,
                tags TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                session_id TEXT,
                promoted INTEGER DEFAULT 0
            )
        """)

        # Create FTS5 virtual table for full-text search
        await self.db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                category,
                tags,
                content='memories',
                content_rowid='id'
            )
        """)

        # Create triggers to keep FTS in sync
        await self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, category, tags)
                VALUES (new.id, new.content, new.category, new.tags);
            END
        """)

        await self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category, tags)
                VALUES ('delete', old.id, old.content, old.category, old.tags);
            END
        """)

        await self.db.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category, tags)
                VALUES ('delete', old.id, old.content, old.category, old.tags);
                INSERT INTO memories_fts(rowid, content, category, tags)
                VALUES (new.id, new.content, new.category, new.tags);
            END
        """)

        # Create sessions table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                started_at REAL NOT NULL,
                ended_at REAL,
                summary TEXT,
                mood TEXT,
                event_count INTEGER DEFAULT 0
            )
        """)

        # Create entities table for graph relationships
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                entity_type TEXT,
                properties TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            )
        """)

        # Create relationships table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                relationship_type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                FOREIGN KEY (source_id) REFERENCES entities(id),
                FOREIGN KEY (target_id) REFERENCES entities(id)
            )
        """)

        await self.db.commit()
        logger.info(f"Memory engine initialized at {self.db_path}")

    async def close(self):
        """Close the database connection."""
        if self.db:
            await self.db.close()

    async def store(
        self,
        content: str,
        category: str = "general",
        importance: int = 5,
        tags: list[str] | None = None,
        session_id: str | None = None,
    ) -> int:
        """Store a new memory. Returns the memory ID."""
        now = time.time()
        tags_json = json.dumps(tags or [])

        cursor = await self.db.execute(
            """
            INSERT INTO memories (content, category, importance, tags, created_at, updated_at, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (content, category, importance, tags_json, now, now, session_id),
        )
        await self.db.commit()
        memory_id = cursor.lastrowid
        logger.debug(f"Stored memory {memory_id}: {content[:50]}...")
        return memory_id

    async def search(
        self,
        query: str,
        limit: int = 10,
        category: str | None = None,
        min_importance: int = 1,
    ) -> list[dict]:
        """Search memories using FTS5."""
        if category:
            sql = """
                SELECT m.id, m.content, m.category, m.importance, m.tags, m.created_at,
                       rank
                FROM memories_fts f
                JOIN memories m ON m.id = f.rowid
                WHERE memories_fts MATCH ? AND m.category = ? AND m.importance >= ?
                ORDER BY rank
                LIMIT ?
            """
            params = (query, category, min_importance, limit)
        else:
            sql = """
                SELECT m.id, m.content, m.category, m.importance, m.tags, m.created_at,
                       rank
                FROM memories_fts f
                JOIN memories m ON m.id = f.rowid
                WHERE memories_fts MATCH ? AND m.importance >= ?
                ORDER BY rank
                LIMIT ?
            """
            params = (query, min_importance, limit)

        async with self.db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "importance": row[3],
                    "tags": json.loads(row[4]),
                    "created_at": row[5],
                }
                for row in rows
            ]

    async def get_recent(self, limit: int = 20, category: str | None = None) -> list[dict]:
        """Get most recent memories."""
        if category:
            sql = """
                SELECT id, content, category, importance, tags, created_at
                FROM memories
                WHERE category = ?
                ORDER BY created_at DESC
                LIMIT ?
            """
            params = (category, limit)
        else:
            sql = """
                SELECT id, content, category, importance, tags, created_at
                FROM memories
                ORDER BY created_at DESC
                LIMIT ?
            """
            params = (limit,)

        async with self.db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "content": row[1],
                    "category": row[2],
                    "importance": row[3],
                    "tags": json.loads(row[4]),
                    "created_at": row[5],
                }
                for row in rows
            ]

    async def generate_context_cache(self) -> str:
        """Generate a lean context summary (~400 tokens) for heartbeat injection."""
        recent = await self.get_recent(limit=10)
        if not recent:
            return "No recent memories yet."

        lines = ["## Recent Context"]
        for mem in recent:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(mem["created_at"]))
            lines.append(f"- [{ts}] [{mem['category']}] {mem['content'][:100]}")

        cache = "\n".join(lines)

        # Truncate to ~400 tokens (~1600 chars)
        if len(cache) > 1600:
            cache = cache[:1597] + "..."

        return cache

    async def create_entity(
        self, name: str, entity_type: str | None = None, properties: dict | None = None
    ) -> int:
        """Create an entity in the knowledge graph."""
        now = time.time()
        props_json = json.dumps(properties or {})

        cursor = await self.db.execute(
            """
            INSERT OR IGNORE INTO entities (name, entity_type, properties, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, entity_type, props_json, now),
        )
        await self.db.commit()

        # Get the ID (either newly created or existing)
        async with self.db.execute(
            "SELECT id FROM entities WHERE name = ?", (name,)
        ) as row:
            result = await row.fetchone()
            return result[0]

    async def add_relationship(
        self,
        source_name: str,
        target_name: str,
        relationship_type: str,
        properties: dict | None = None,
    ) -> int:
        """Add a relationship between two entities."""
        source_id = await self.create_entity(source_name)
        target_id = await self.create_entity(target_name)
        now = time.time()
        props_json = json.dumps(properties or {})

        cursor = await self.db.execute(
            """
            INSERT INTO relationships (source_id, target_id, relationship_type, properties, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_id, target_id, relationship_type, props_json, now),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def get_entity_relationships(self, name: str) -> list[dict]:
        """Get all relationships for an entity."""
        async with self.db.execute(
            "SELECT id FROM entities WHERE name = ?", (name,)
        ) as row:
            entity = await row.fetchone()
            if not entity:
                return []

        entity_id = entity[0]

        sql = """
            SELECT e.name, r.relationship_type, e2.name, r.properties
            FROM relationships r
            JOIN entities e ON e.id = r.source_id
            JOIN entities e2 ON e2.id = r.target_id
            WHERE r.source_id = ? OR r.target_id = ?
        """

        async with self.db.execute(sql, (entity_id, entity_id)) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "from": row[0],
                    "type": row[1],
                    "to": row[2],
                    "properties": json.loads(row[3]),
                }
                for row in rows
            ]
