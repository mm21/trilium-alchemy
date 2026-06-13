"""
Note metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    model_serializer,
    model_validator,
)

from ...core.attribute import BaseAttribute, Label, Relation
from ...core.branch import Branch
from ...core.note.note import Note
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

            value = attribute._model.get_field("value", str)
            attributes.append(
                AttributeMeta(
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

    def to_note(self, src_dir: Path, session: Session) -> Note:
        """
        Populate note from this model.
        """
        note = Note(note_id=self.note_id, session=session)
        note.title = self.title
        note.note_type = self.note_type
        note.mime = self.mime

        # update content if out of date
        if note.blob_id != self.blob_id:
            content_file = src_dir / f"content.{'txt' if note.is_string else 'bin'}"
            assert content_file.is_file()

            note.content = (
                content_file.read_text()
                if note.is_string
                else content_file.read_bytes()
            )

        # set attributes
        note.attributes.owned = self._load_attributes(note)

        # set children
        note.branches.children = self._load_child_branches(note)

        return note

    def _load_attributes(self, note: Note) -> list[BaseAttribute]:
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

        def get_attr[T: BaseAttribute](
            name: str, attr_dict: dict[str, list[T]]
        ) -> T | None:
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

        for attr_meta in self.attributes:
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

                relation.target = Note(note_id=attr_meta.value, session=note.session)
                relation.inheritable = attr_meta.inheritable
                attributes.append(relation)

        return attributes

    def _load_child_branches(self, note: Note) -> list[Branch]:
        """
        Get child branches from metadata.
        """
        assert note.note_id

        branches: list[Branch] = []

        for branch_meta in self.children:
            branch_id = Branch._gen_branch_id(note.note_id, branch_meta.child_note_id)
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


class AttributeMeta(BaseModel):
    """
    Attribute metadata used to populate yaml.

    Position is inferred from the order in the containing list.
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
    Branch metadata used to populate yaml.

    Position is inferred from the order in the containing list, and branch id is
    inferred from the parent and child note ids. Expanded state is ignored, being
    primarily a UI concept only.
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
