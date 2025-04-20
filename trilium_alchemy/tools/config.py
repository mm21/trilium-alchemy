"""
Interface to configuration as persisted in .yaml file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, field_validator, model_validator

from ..core import Session

__all__ = [
    "Config",
    "InstanceConfig",
    "get_config",
]


class Config(BaseModel):
    """
    Encapsulates configuration for use in tools.
    """

    instances: dict[str, InstanceConfig]

    root_data_dir: Path | None = None
    """
    Root folder for per-instance Trilium data dirs.
    """

    @field_validator("root_data_dir", mode="before")
    def validate_root_data_dir(cls, value: Any) -> Any:
        return _validate_dir(value)

    @model_validator(mode="after")
    def validate_instances(self) -> Self:
        # propagate data dir to instances if applicable
        if self.root_data_dir:
            for instance_name, instance in self.instances.items():
                if not instance.data_dir:
                    data_dir = self.root_data_dir / instance_name
                    _validate_dir(data_dir)

                    instance.data_dir = data_dir
        return self


class InstanceConfig(BaseModel):
    """
    Encapsulates info for a Trilium instance.
    """

    host: str
    token: str | None = None
    password: str | None = None
    data_dir: Path | None = None
    root_note_fqcn: str | None = None

    @field_validator("data_dir", mode="before")
    def validate_data_dir(cls, value: Any) -> Any:
        return _validate_dir(value)

    @model_validator(mode="after")
    def validate_token_or_password(self) -> Self:
        if not (self.token or self.password):
            raise ValueError("either token or password must be provided")
        return self

    def create_session(self) -> Session:
        """
        Get session from this instance's fields.
        """
        return Session(
            self.host, token=self.token, password=self.password, default=False
        )


def get_config(file: Path) -> Config:
    """
    Get config info from given path.
    """
    if not file.is_file():
        raise ValueError(f"file does not exist: '{file}'")

    with file.open() as fh:
        data = yaml.safe_load(fh)

    return Config(**data)


def _validate_dir(value: Any) -> Any:
    """
    Coerce to path and ensure it exists.
    """
    if not isinstance(value, (str, Path)):
        # let pydantic handle type error
        return value

    path = Path(value) if isinstance(value, str) else value

    if not path.is_dir():
        raise ValueError(f"folder does not exist: '{path}'")

    return path
