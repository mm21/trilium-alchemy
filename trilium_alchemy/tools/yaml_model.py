"""
Interface to create models with associated .yaml storage.
"""

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel

__all__ = [
    "BaseYamlModel",
]


class BaseYamlModel(BaseModel):
    """
    Base pydantic model with additional functionality to load to and dump from
    .yaml file.
    """

    @classmethod
    def load_yaml(cls, file: Path) -> Self:
        """
        Load model from .yaml file.
        """
        assert file.is_file()

        with file.open() as fh:
            model = yaml.safe_load(fh)

        if not isinstance(model, dict):
            raise ValueError(f"Invalid yaml contents: {model}")

        return cls(**model)

    def dump_yaml(self, file: Path):
        """
        Dump model to .yaml file.
        """
        model = self.model_dump(by_alias=True)
        model_yaml = yaml.safe_dump(
            model, default_flow_style=False, sort_keys=False
        )
        file.write_text(model_yaml)
