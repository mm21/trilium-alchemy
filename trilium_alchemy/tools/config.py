"""
Interface to configuration as persisted in .yaml file.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

__all__ = [
    "Config",
    "TriliumInstance",
    "get_config",
]


class Config(BaseModel):
    """
    Encapsulates configuration for use in tools.
    """

    instances: dict[str, TriliumInstance]

    root_data_dir: str
    """
    Root folder for per-instance Trilium data dirs.
    """

    root_backup_dir: str | None = None
    """
    Root folder for per-instance Trilium backup dirs.
    """


class TriliumInstance(BaseModel):
    """
    Encapsulates info for a Trilium instance.
    """

    host: str
    token: str | None = None
    password: str | None = None
    declarative_root: str | None = None

    @model_validator(mode="after")
    def check_token_or_password(self):
        if not (self.token or self.password):
            raise ValueError("Either token or password must be provided")
        return self


def get_config(file: Path) -> Config:
    """
    Get config info from given path.
    """
    assert file.is_file()

    with file.open() as fh:
        data = yaml.safe_load(fh)

    return Config(**data)
