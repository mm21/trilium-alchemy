"""
Filesystem representation of a single note.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    model_serializer,
    model_validator,
)

from .content import get_digest

if TYPE_CHECKING:
    from ..session import Session
    from .note import Note

__all__ = [
    "METADATA_FILENAME",
    "dump_note",
]

METADATA_FILENAME = "meta.yaml"
"""
Filename containing metadata for filesystem format.
"""


class NoteMetadata(BaseModel):
    """
    Note metadata used to populate yaml.
    """

    title: str
    blob_id: str
    attributes: list[AttributeMetadata]
    children: list[BranchMetadata]
    note_type: str = Field(
        validation_alias=AliasChoices("note_type", "type"),
        serialization_alias="type",
    )
    mime: str
    note_id: str = Field(
        validation_alias=AliasChoices("note_id", "id"), serialization_alias="id"
    )

    @classmethod
    def from_note(cls, note: Note) -> NoteMetadata:
        """
        Populate model from a note.
        """
        assert note.note_id

        attributes: list[AttributeMetadata] = []
        children: list[BranchMetadata] = []

        for attribute in note.attributes.owned:
            assert attribute.attribute_id

            value = attribute._model.get_field("value")
            assert isinstance(value, str)

            attributes.append(
                AttributeMetadata(
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
                BranchMetadata(
                    note_id=branch.child.note_id,
                    prefix=branch.prefix,
                )
            )

        return NoteMetadata(
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


class AttributeMetadata(BaseModel):
    """
    Attribute metadata used to populate yaml. Position is inferred from the
    order in the containing list.
    """

    attribute_type: str
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


class BranchMetadata(BaseModel):
    """
    Branch metadata used to populate yaml. Position is inferred from the
    order in the containing list, and branch id is inferred from
    the parent and child note ids. Expanded state is ignored, being primarily
    a UI concept only.
    """

    note_id: str
    prefix: str

    @model_serializer
    def to_str(self) -> str:
        return f"{self.note_id}|{self.prefix}"

    @model_validator(mode="before")
    @classmethod
    def from_str(cls, data: Any) -> Any:
        if not isinstance(data, str):
            return data

        note_id, prefix = data.split("|", maxsplit=1)
        return {
            "note_id": note_id,
            "prefix": prefix,
        }


def dump_note(note: Note, dest_dir: Path, *, check_content_hash: bool = False):
    """
    Dump note to destination folder.
    """

    # collect files/folders in destination besides meta.yaml
    extra_paths: list[Path] = [
        p for p in dest_dir.iterdir() if not p.name == METADATA_FILENAME
    ]

    # ensure there are no unexpected contents in destination
    if len(extra_paths) > 1 or not all(
        p.is_file() and p.name in ["content.txt", "content.bin"]
        for p in extra_paths
    ):
        raise Exception(
            f"Unexpected files in export destination '{dest_dir}': {extra_paths}"
        )

    # get metadata
    metadata = NoteMetadata.from_note(note)

    # convert metadata to yaml string
    metadata_dict = metadata.model_dump(by_alias=True)
    metadata_str = yaml.safe_dump(
        metadata_dict, default_flow_style=False, sort_keys=False
    )

    # write metadata if it differs from any existing metadata
    metadata_path = dest_dir / METADATA_FILENAME
    if not metadata_path.is_file() or metadata_path.read_text() != metadata_str:
        metadata_path.write_text(metadata_str)

    # get path to content file for this note
    content_path = dest_dir / f"content.{'txt' if note.is_string else 'bin'}"

    # write content if it doesn't exist or is out of date
    blob_id = (
        get_digest(content_path.read_bytes())
        if check_content_hash
        else metadata.blob_id
    )
    if not content_path.exists() or blob_id != note.blob_id:
        if note.is_string:
            content_path.write_text(note.content_str)
        else:
            content_path.write_bytes(note.content_bin)

    # prune extra files if different from content_path
    # - would only occur if note content type was changed
    for path in [p for p in extra_paths if p.name != content_path.name]:
        path.unlink()
