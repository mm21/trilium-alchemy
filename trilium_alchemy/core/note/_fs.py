"""
Filesystem representation of a single note.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    model_serializer,
    model_validator,
)

from ..attribute import BaseAttribute, Label, Relation
from ..branch import Branch
from ..session import Session
from .content import get_digest
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
    def from_file(cls, file: Path) -> NoteMetadata:
        """
        Populate model from .yaml file.
        """
        assert file.is_file()

        with file.open() as fh:
            data_dict = yaml.safe_load(fh)
        return NoteMetadata(**data_dict)

    def to_file(self, file: Path):
        """
        Write model to .yaml file.
        """
        data_dict = self.model_dump(by_alias=True)
        data_str = yaml.safe_dump(
            data_dict, default_flow_style=False, sort_keys=False
        )
        file.write_text(data_str)

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
                    child_note_id=branch.child.note_id,
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


class BranchMetadata(BaseModel):
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


def dump_note(dest_dir: Path, note: Note, *, check_content_hash: bool = False):
    """
    Dump note to destination folder.
    """

    # collect files/folders in destination besides meta.yaml
    extra_paths: list[Path] = [
        p for p in dest_dir.iterdir() if not p.name == METADATA_FILENAME
    ]

    # ensure there are no unexpected contents in destination
    if not all(
        p.is_file() and p.name in ["content.txt", "content.bin"]
        for p in extra_paths
    ):
        raise Exception(
            f"Unexpected files in export destination '{dest_dir}': {extra_paths}"
        )

    meta_path = dest_dir / METADATA_FILENAME
    current_meta: NoteMetadata | None = None

    # get note metadata
    meta = NoteMetadata.from_note(note)

    # get metadata from file
    if meta_path.exists():
        current_meta = NoteMetadata.from_file(meta_path)

    # write metadata if it doesn't exist or differs from existing metadata
    if meta != current_meta:
        meta.to_file(meta_path)

    # get path to content file for this note
    content_file = dest_dir / f"content.{'txt' if note.is_string else 'bin'}"

    # write content if it doesn't exist or is out of date
    current_blob_id = (
        get_digest(content_file.read_bytes())
        if check_content_hash
        else (current_meta.blob_id if current_meta else None)
    )
    if not content_file.exists() or current_blob_id != note.blob_id:
        if note.is_string:
            content_file.write_text(note.content_str)
        else:
            content_file.write_bytes(note.content_bin)

    # prune extra files if different from content_path
    # - would only occur if note content type was changed
    for path in [p for p in extra_paths if p.name != content_file.name]:
        path.unlink()


def load_note(src_dir: Path, session: Session) -> Note:
    """
    Load note from source folder.
    """

    meta_path = src_dir / METADATA_FILENAME
    assert meta_path.is_file()

    # get metadata from file
    meta = NoteMetadata.from_file(meta_path)

    note = Note(note_id=meta.note_id, session=session)
    note.title = meta.title
    note.note_type = meta.note_type
    note.mime = meta.mime

    # update content if out of date
    if note.blob_id != meta.blob_id:
        content_file = src_dir / f"content.{'txt' if note.is_string else 'bin'}"
        assert content_file.is_file()

        note.content = (
            content_file.read_text()
            if note.is_string
            else content_file.read_bytes()
        )

    # set attributes
    note.attributes.owned = _load_attributes(note, meta)

    # set children
    note.branches.children = _load_child_branches(note, meta)

    return note


def _load_attributes(note: Note, meta: NoteMetadata) -> list[BaseAttribute]:
    """
    Get note's attributes from metadata, updating any existing attributes.
    """

    def add_attr[T: BaseAttribute](attr: T, attr_dict: dict[str, list[T]]):
        """
        Add existing attribute to mapping.
        """
        if attr.name in attr_dict:
            attr_dict[attr.name].append(attr)
        else:
            attr_dict[attr.name] = [attr]

    def get_attr[
        T: BaseAttribute
    ](name: str, attr_dict: dict[str, list[T]]) -> T | None:
        """
        Get and remove first existing attribute with the given name.
        """
        if name not in attr_dict or not len(attr_dict[name]):
            return None
        return attr_dict[name].pop(0)

    # create mappings of current attribute names to objects, grouped by type
    current_labels: dict[str, list[Label]] = {}
    current_relations: dict[str, list[Relation]] = {}

    for label in note.labels.owned:
        add_attr(label, current_labels)

    for relation in note.relations.owned:
        add_attr(relation, current_relations)

    # create attributes from metadata
    attributes: list[BaseAttribute] = []

    for attr_meta in meta.attributes:
        if attr_meta.attribute_type == "label":
            label = get_attr(attr_meta.name, current_labels) or Label(
                attr_meta.name, session=note.session
            )

            label.value = attr_meta.value
            label.inheritable = attr_meta.inheritable
            attributes.append(label)
        else:
            relation = get_attr(attr_meta.name, current_relations) or Relation(
                attr_meta.name, session=note.session
            )

            relation.target = Note(
                note_id=attr_meta.value, session=note.session
            )
            relation.inheritable = attr_meta.inheritable
            attributes.append(relation)

    return attributes


def _load_child_branches(note: Note, meta: NoteMetadata) -> list[Branch]:
    """
    Get child branches from metadata.
    """
    assert note.note_id

    branches: list[Branch] = []

    for branch_meta in meta.children:
        branch_id = Branch._gen_branch_id(
            note.note_id, branch_meta.child_note_id
        )
        child = Note(note_id=branch_meta.child_note_id, session=note.session)
        branch = Branch(
            parent=note,
            child=child,
            prefix=branch_meta.prefix,
            session=note.session,
            _branch_id=branch_id,
            _ignore_expanded=True,
        )

        branches.append(branch)

    return branches
