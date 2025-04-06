"""
Interface to configuration as persisted in .yaml file.
"""
from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

__all__ = [
    "Config",
    "TriliumInstance",
    "get_config",
]


class Config(BaseModel):
    """
    Encapsulates configuration for use in tools.
    """

    instances: dict[str, TriliumInstance] | None
    backup_dir: str | None


class TriliumInstance(BaseModel):
    """
    Encapsulates info for a Trilium instance.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "anyOf": [{"required": ["token"]}, {"required": ["password"]}]
        }
    )

    host: str
    token: str | None
    password: str | None
    data_dir: str | None


# temp for testing
if __name__ == "__main__":
    schema = Config.model_json_schema()

    with open("__out__/user_schema.json", "w") as f:
        json.dump(schema, indent=2, fp=f)
