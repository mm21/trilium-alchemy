"""
Implements Trilium-specific handling of flush.
"""

from __future__ import annotations

from graphlib import TopologicalSorter
from typing import TYPE_CHECKING, Iterable

from alchemizer import State

from .utils import INHERIT_RELATIONS

if TYPE_CHECKING:
    from .attribute.relation import Relation
    from .entity.entity import BaseEntity
    from .note.note import Note


def add_branch_dependencies(
    dirty_set: set[BaseEntity], sorter: TopologicalSorter[BaseEntity]
):
    """
    Add dependency of all deleted branches on all created branches.

    This avoids any notes being accidentally deleted by an ancestor being deleted.
    """
    from .branch.branch import Branch

    branches = {b for b in dirty_set if isinstance(b, Branch)}
    created_branches = {b for b in branches if b.state is State.CREATE}
    deleted_branches = {b for b in branches if b.state is State.DELETE}

    for branch_deleted in deleted_branches:
        for branch_created in created_branches:
            sorter.add(branch_deleted, branch_created)


def check_refresh_ordering(dirty_set: set[BaseEntity]) -> set[Note]:
    """
    Return set of notes with changed child branch positions.

    These need to be refreshed in the UI after they're flushed.
    """
    from .branch.branch import Branch

    notes: set[Note] = set()

    for entity in dirty_set:
        if isinstance(entity, Branch):
            if entity._model.is_field_changed("note_position"):
                if not entity.parent._is_delete:
                    notes.add(entity.parent)

    return notes


def check_refresh_notes(dirty_set: set[BaseEntity]) -> set[Note]:
    """
    Return set of notes with changed relations which affect inherited attributes or
    children.

    These need to be refreshed to pick up changes to inherited attributes and
    automatically-added children (from new templates).
    """
    from .note.note import Note

    notes: set[Note] = set()

    for entity in dirty_set:
        if isinstance(entity, Note) and not entity._is_delete:
            # check for created/deleted inherit relations
            relations: list[Relation] = []

            for relation in INHERIT_RELATIONS:
                relations += entity.relations.get_all(relation)

            if any(
                r._is_create or r._is_delete or r._model.is_field_changed("value")
                for r in relations
            ):
                notes.add(entity)

    return notes


def count_entities(entities: Iterable[BaseEntity]) -> dict[str, int]:
    """
    Return a mapping of entity type name to the number of entities of that type.
    """
    counts = {name: 0 for name in _ENTITY_TYPE_NAMES}
    for entity in entities:
        counts[_get_type_name(entity)] += 1
    return counts


def get_summary(entities: Iterable[BaseEntity]) -> str:
    """
    Return a brief summary of how many entities are in each state.
    """
    states = (State.CREATE, State.UPDATE, State.DELETE)
    index = {name: {state: 0 for state in states} for name in _ENTITY_TYPE_NAMES}

    for entity in entities:
        index[_get_type_name(entity)][entity._state] += 1

    # get (create/update/delete) counts
    counts = ", ".join(
        f"{'/'.join(str(index[name][state]) for state in states)} {name}"
        for name in _ENTITY_TYPE_NAMES
    )
    return f"(create/update/delete) {counts}"


_ENTITY_TYPE_NAMES = ("notes", "attributes", "branches", "attachments")
"""
Names of entity types for use in summaries.
"""


def _get_type_name(entity: BaseEntity) -> str:
    """
    Get the name of this entity's type for use in summaries.
    """
    from .attribute.attribute import BaseAttribute
    from .branch.branch import Branch
    from .note.attachments import Attachment
    from .note.note import Note

    for cls, name in zip(
        (Note, BaseAttribute, Branch, Attachment), _ENTITY_TYPE_NAMES, strict=True
    ):
        if isinstance(entity, cls):
            return name

    raise TypeError(f"Unexpected entity type: {type(entity)}")
