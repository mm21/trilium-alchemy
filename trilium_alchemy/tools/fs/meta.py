"""
Note metadata.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    model_serializer,
    model_validator,
)

from ...core.note import Note
from ...core.session import Session
from ..yaml_model import BaseYamlModel

__all__ = [
    "META_FILENAME",
    "NoteMeta",
]

META_FILENAME = "meta.yaml"
"""
Filename containing metadata for filesystem format.
"""


class NoteMeta(BaseYamlModel):
    """
    Note metadata used to populate yaml.
    """

    note_id: str = Field(
        validation_alias=AliasChoices("note_id", "id"), serialization_alias="id"
    )
    note_type: str = Field(
        validation_alias=AliasChoices("note_type", "type"),
        serialization_alias="type",
    )
    mime: str
    title: str
    blob_id: str
    attributes: list[AttributeMeta]
    children: list[BranchMeta]

    @classmethod
    def from_note(cls, note: Note) -> NoteMeta:
        """
        Populate model from a note.
        """
        assert note.note_id

        attributes: list[AttributeMeta] = []
        children: list[BranchMeta] = []

        for attribute in note.attributes.owned:
            assert attribute.attribute_id

            value = attribute._model.get_field("value")
            assert isinstance(value, str)

            attributes.append(
                AttributeMeta(
                    attribute_id=attribute.attribute_id,
                    attribute_type=attribute._attribute_type,
                    name=attribute.name,
                    value=value,
                    inheritable=attribute.inheritable,
                )
            )

        for branch in note.branches.children:
            assert branch.branch_id
            assert branch.child.note_id

            children.append(
                BranchMeta(
                    child_note_id=branch.child.note_id,
                    prefix=branch.prefix,
                )
            )

        return NoteMeta(
            title=note.title,
            blob_id=note.blob_id,
            attributes=attributes,
            children=children,
            note_type=note.note_type,
            mime=note.mime,
            note_id=note.note_id,
        )

    def to_note(self, session: Session) -> Note:
        """
        Populate note from this model.
        """


class AttributeMeta(BaseModel):
    """
    Attribute metadata used to populate yaml. Position is inferred from the
    order in the containing list.
    """

    attribute_type: Literal["label", "relation"]
    name: str
    value: str
    inheritable: bool

    @model_serializer
    def to_str(self) -> str:
        type_prefix = "~" if self.attribute_type == "relation" else ""
        inheritable = "(inheritable)" if self.inheritable else ""
        return f"{type_prefix}{self.name}{inheritable}={self.value}"

    @model_validator(mode="before")
    @classmethod
    def from_str(cls, data: Any) -> Any:
        if not isinstance(data, str):
            return data

        spec, value = data.split("=", maxsplit=1)

        if spec.startswith("~"):
            attribute_type = "relation"
            spec = spec[1:]
        else:
            attribute_type = "label"

        if spec.endswith("(inheritable)"):
            inheritable = True
            spec = spec.replace("(inheritable)", "")
        else:
            inheritable = False

        name = spec

        return {
            "attribute_type": attribute_type,
            "name": name,
            "value": value,
            "inheritable": inheritable,
        }


class BranchMeta(BaseModel):
    """
    Branch metadata used to populate yaml. Position is inferred from the
    order in the containing list, and branch id is inferred from
    the parent and child note ids. Expanded state is ignored, being primarily
    a UI concept only.
    """

    child_note_id: str
    prefix: str

    @model_serializer
    def to_str(self) -> str:
        return f"{self.child_note_id}|{self.prefix}"

    @model_validator(mode="before")
    @classmethod
    def from_str(cls, data: Any) -> Any:
        if not isinstance(data, str):
            return data

        child_note_id, prefix = data.split("|", maxsplit=1)
        return {
            "child_note_id": child_note_id,
            "prefix": prefix,
        }
