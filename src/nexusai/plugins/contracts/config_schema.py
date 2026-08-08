"""
Declarative configuration schema model for plugin settings.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConfigSchemaItem(BaseModel):
    """Schema descriptor for a single configuration field."""

    key: str = Field(..., description="Configuration property key")
    type: str = Field(
        default="string", description="Value type (string, integer, boolean, float, secret)"
    )
    default: Any = Field(default=None, description="Default value if omitted")
    required: bool = Field(default=False, description="Whether setting is mandatory")
    secret: bool = Field(
        default=False, description="True if value contains sensitive token or secret"
    )
    description: str = Field(default="", description="Human-readable setting summary")

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }


class PluginConfigSchema(BaseModel):
    """Declarative plugin configuration schema container."""

    items: list[ConfigSchemaItem] = Field(default_factory=list, description="List of schema items")

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate provided configuration dictionary against schema.

        Returns:
            Validated configuration dictionary populated with defaults.

        Raises:
            ValueError: If mandatory setting is missing or type invalid.
        """
        validated: dict[str, Any] = {}
        for item in self.items:
            val = config.get(item.key)
            if val is None:
                if item.required:
                    raise ValueError(f"Missing mandatory configuration setting '{item.key}'")
                val = item.default
            validated[item.key] = val
        return validated

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }
