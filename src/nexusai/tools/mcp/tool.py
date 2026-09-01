"""Dynamic McpToolWrapper adapting MCP tool specifications into NexusAI BaseTool instances."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model

from nexusai.core.errors import ToolExecutionError
from nexusai.security.guard import RiskLevel
from nexusai.tools.base import BaseTool
from nexusai.tools.mcp.client import McpClient
from nexusai.tools.mcp.models import McpToolDefinition


def _build_pydantic_model_from_schema(model_name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Dynamically generate a Pydantic BaseModel from an MCP tool JSON schema."""
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    fields: dict[str, Any] = {}

    type_mapping: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    for prop_name, prop_meta in properties.items():
        if not isinstance(prop_meta, dict):
            fields[prop_name] = (Any, Field(default=None))
            continue

        raw_type = prop_meta.get("type", "any")
        py_type = type_mapping.get(raw_type, Any)
        prop_desc = prop_meta.get("description", "")

        is_required = prop_name in required_fields
        default_val = ... if is_required else prop_meta.get("default", None)

        fields[prop_name] = (
            py_type if is_required else py_type | None,
            Field(default=default_val, description=prop_desc),
        )

    if not fields:

        class GenericMcpInput(BaseModel):
            """Fallback input model for tools with no explicit parameter schema."""

            model_config = ConfigDict(extra="allow")

        GenericMcpInput.__name__ = model_name
        return GenericMcpInput

    return create_model(model_name, **fields)


class McpToolWrapper(BaseTool):
    """Dynamic tool wrapper adapting an external MCP tool into NexusAI's BaseTool interface."""

    def __init__(
        self,
        client: McpClient,
        definition: McpToolDefinition,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        namespace_prefix: str | None = None,
    ) -> None:
        self.client = client
        self.mcp_tool_name = definition.name
        self.definition = definition
        self.risk_level = risk_level

        # Namespace tool name to avoid collisions if prefix provided
        if namespace_prefix:
            self.name = f"{namespace_prefix}_{definition.name}"
        else:
            self.name = definition.name

        self.description = (
            definition.description or f"MCP tool '{definition.name}' from {client.server_name}"
        )
        self._raw_input_schema = definition.input_schema or {}

        # Build dynamic Pydantic schema for validation
        clean_model_name = (
            "".join(part.capitalize() for part in self.name.replace("-", "_").split("_"))
            + "InputSchema"
        )
        self.input_schema = _build_pydantic_model_from_schema(
            clean_model_name, self._raw_input_schema
        )

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the remote MCP tool via the active client connection."""
        if not self.client.is_connected:
            raise ToolExecutionError(
                f"Cannot execute MCP tool '{self.name}': Server '{self.client.server_name}' is not connected"
            )

        call_args = dict(kwargs)
        result = await self.client.call_tool(self.mcp_tool_name, call_args)

        if result.is_error:
            err_text = result.extract_text() or "Unknown MCP execution error"
            raise ToolExecutionError(
                f"MCP tool '{self.name}' reported failure: {err_text}",
                details={
                    "server": self.client.server_name,
                    "raw_content": str([c.model_dump() for c in result.content]),
                },
            )

        text_content = result.extract_text()
        if text_content:
            return text_content

        # If non-text or multiple items, return raw content list
        return [item.model_dump(exclude_none=True) for item in result.content]

    def to_json_schema(self) -> dict[str, Any]:
        """Export tool schema to LLM function calling specification."""
        params = (
            self._raw_input_schema
            if self._raw_input_schema
            else self.input_schema.model_json_schema()
        )
        # Clean title to keep schema clean for LLM
        if isinstance(params, dict):
            params = dict(params)
            params.pop("title", None)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }
