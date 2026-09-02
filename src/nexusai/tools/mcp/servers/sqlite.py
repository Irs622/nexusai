"""Built-in SQLite MCP Server providing async database querying and schema inspection."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import re
from typing import Any

import aiosqlite

from nexusai.tools.mcp.servers.base import McpServerBase


class SqliteMcpServer(McpServerBase):
    """MCP Server exposing SQLite query execution and schema inspection tools via aiosqlite."""

    def __init__(self, db_path: str | Path = "storage/nexus.db") -> None:
        super().__init__(
            name="nexus-sqlite",
            version="1.0.0",
            description="NexusAI Asynchronous SQLite MCP Server",
        )
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            p = Path(self.db_path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(p)

        self._register_sqlite_tools()

    def _register_sqlite_tools(self) -> None:
        # 1. read_query
        self.register_tool(
            name="read_query",
            description="Execute a SELECT SQL query on the SQLite database and return rows.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query to execute",
                    },
                    "params": {
                        "type": "array",
                        "description": "Optional parameterized query values",
                        "default": [],
                    },
                },
                "required": ["query"],
            },
            handler=self._handle_read_query,
        )

        # 2. write_query
        self.register_tool(
            name="write_query",
            description="Execute an INSERT, UPDATE, DELETE, or DDL query and commit changes.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL mutation or DDL query to execute",
                    },
                    "params": {
                        "type": "array",
                        "description": "Optional parameterized query values",
                        "default": [],
                    },
                },
                "required": ["query"],
            },
            handler=self._handle_write_query,
        )

        # 3. list_tables
        self.register_tool(
            name="list_tables",
            description="List all user tables and views in the database.",
            input_schema={
                "type": "object",
                "properties": {},
            },
            handler=self._handle_list_tables,
        )

        # 4. describe_table
        self.register_tool(
            name="describe_table",
            description="Get column definitions and schema information for a specific table.",
            input_schema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table to describe",
                    }
                },
                "required": ["table_name"],
            },
            handler=self._handle_describe_table,
        )

    async def _handle_read_query(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args["query"]).strip()
        params = list(args.get("params", []))

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                description = cursor.description or ()
                columns = [col[0] for col in description]
                result_rows = [dict(row) for row in rows]

                return {
                    "columns": columns,
                    "rows": result_rows,
                    "count": len(result_rows),
                }

    async def _handle_write_query(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args["query"]).strip()
        params = list(args.get("params", []))

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                await db.commit()
                return {
                    "rows_affected": cursor.rowcount,
                    "last_row_id": cursor.lastrowid,
                    "status": "committed",
                }

    async def _handle_list_tables(self, _args: dict[str, Any]) -> list[dict[str, Any]]:
        query = """
            SELECT name, type, sql
            FROM sqlite_master
            WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
            ORDER BY name ASC;
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def _handle_describe_table(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        table_name = str(args["table_name"]).strip()
        # Sanitize table name (only alphanumeric and underscores)
        if not re.match(r"^[A-Za-z0-9_]+$", table_name):
            raise ValueError(f"Invalid table name format: '{table_name}'")

        query = f"PRAGMA table_info({table_name});"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]


def main() -> None:
    """CLI entry point for running SQLite MCP Server."""
    parser = argparse.ArgumentParser(description="NexusAI Asynchronous SQLite MCP Server")
    parser.add_argument(
        "--db-path",
        type=str,
        default=os.environ.get("NEXUS_SQLITE_PATH", "storage/nexus.db"),
        help="Path to SQLite database file or ':memory:' (default: storage/nexus.db)",
    )
    args = parser.parse_args()

    server = SqliteMcpServer(db_path=args.db_path)
    server.log(f"Initialized with SQLite database: {server.db_path}")
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
