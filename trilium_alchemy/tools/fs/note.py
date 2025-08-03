"""
Filesystem operations on a single note.
"""
from __future__ import annotations

import logging
from logging import Logger
from pathlib import Path

from ...core.attribute import BaseAttribute, Label, Relation
from ...core.branch import Branch
from ...core.note import Note
from ...core.note.content import get_digest
from ...core.session import Session
from .meta import META_FILENAME, NoteMeta

__all__ = [
    "dump_note",
    "load_note",
]


def dump_note(
    dest_dir: Path,
    note: Note,
    *,
    logger: Logger | None = None,
    check_content_hash: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Dump note to destination folder, returning whether the folder was updated.
    """
    assert dest_dir.is_dir()

    logger = logger or logging.getLogger()
    updated = False

    # collect files/folders in destination besides meta.yaml
    extra_paths: list[Path] = [
        p for p in dest_dir.iterdir() if not p.name == META_FILENAME
    ]

    # ensure there are no unexpected contents in destination
    if not all(
        p.is_file() and p.name in ["content.txt", "content.bin"]
        for p in extra_paths
    ):
        raise Exception(
            f"Unexpected files in export destination '{dest_dir}': {extra_paths}"
        )

    meta_path = dest_dir / META_FILENAME
    current_meta: NoteMeta | None = None

    # get note metadata
    meta = NoteMeta.from_note(note)

    # get metadata from file
    if meta_path.exists():
        current_meta = NoteMeta.load_yaml(meta_path)

    # write metadata if it doesn't exist or differs from existing metadata
    if meta != current_meta:
        if dry_run:
            logger.info(
                f"Would write metadata for {note._str_short}: '{meta_path}'"
            )
        else:
            meta.dump_yaml(meta_path)
        updated = True

    # get path to content file for this note
    content_file = dest_dir / f"content.{'txt' if note.is_string else 'bin'}"

    # write content if it doesn't exist or is out of date
    current_blob_id = (
        get_digest(content_file.read_bytes())
        if check_content_hash
        else (current_meta.blob_id if current_meta else None)
    )
    if not content_file.exists() or current_blob_id != note.blob_id:
        if dry_run:
            logger.info(
                f"Would write content for {note._str_short}: '{meta_path}'"
            )
        else:
            if note.is_string:
                content_file.write_text(note.content_str)
            else:
                content_file.write_bytes(note.content_bin)
        updated = True

    # prune extra files if different from content_path
    # - would only occur if note content type was changed
    for path in [p for p in extra_paths if p.name != content_file.name]:
        if dry_run:
            logger.info(
                f"Would delete obsolete content file for {note._str_short}: '{path}'"
            )
        else:
            path.unlink()

    return updated


def load_note(src_dir: Path, session: Session) -> Note:
    """
    Load note from source folder.
    """

    meta_path = src_dir / META_FILENAME
    assert meta_path.is_file()

    # get metadata from file
    meta = NoteMeta.load_yaml(meta_path)

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


def _load_attributes(note: Note, meta: NoteMeta) -> list[BaseAttribute]:
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


def _load_child_branches(note: Note, meta: NoteMeta) -> list[Branch]:
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
