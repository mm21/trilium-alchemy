"""
Implements a cache of Trilium entities.
"""

from __future__ import annotations

from typing import overload, TypeVar, Generic, Type, Any, Iterable
import graphlib
import logging

import trilium_alchemy
from .exceptions import ValidationError, _ValidationError
from . import session


class Cache:
    """
    Combines a cache and unit of work collection. Maintains changes made by user
    and synchronizes with Trilium upon flush.
    """

    entity_map: dict[str, trilium_alchemy.core.entity.Entity]
    """Mapping of entity id to entity object"""

    dirty_set: set[trilium_alchemy.core.entity.Entity]
    """Set of objects which need to be synchronized with Trilium"""

    _session: session.Session

    def __init__(self, session: session.Session):
        self._session = session
        self.entity_map = dict()
        self.dirty_set = set()

    def __str__(self):
        return (
            f"Cache: entity_map={self.entity_map}, dirty_set={self.dirty_set}"
        )

    def flush(
        self,
        entities: Iterable[trilium_alchemy.core.entity.Entity] | None = None,
    ):
        """
        Flushes provided entities and all dependencies, or all dirty entities
        if entities not provided.
        """

        entities_iter: Iterable[trilium_alchemy.core.entity.Entity]

        entities_iter = self.dirty_set if entities is None else entities

        # filter by dirty state
        dirty_set = {entity for entity in entities_iter if entity._is_dirty}

        # first pass validation of entities provided by user
        self._validate(dirty_set)

        # save a reference so we can get entities newly added as dependencies
        dirty_set_old = dirty_set.copy()

        # recursively merge in all dependencies
        for entity in dirty_set_old:
            self._flush_gather(entity, dirty_set)

        # validate newly added entities
        self._validate(dirty_set - dirty_set_old)

        logging.info(
            f"Flushing {len(dirty_set)} entities: (create/update/delete) {self._summary(dirty_set)}"
        )

        # create topological sorter
        sorter: graphlib.TopologicalSorter = graphlib.TopologicalSorter()

        # populate and prepare sorter
        for entity in dirty_set:
            sorter.add(entity)

            for dep in entity._dependencies:
                if dep._is_dirty:
                    sorter.add(entity, dep)

        # add dependency of all deleted branches on all created
        # branches. this avoids any notes being accidentally
        # deleted by an ancestor being deleted
        branches = {
            b
            for b in dirty_set
            if isinstance(b, trilium_alchemy.core.branch.Branch)
        }
        created_branches = {
            b
            for b in branches
            if b.state is trilium_alchemy.core.entity.types.State.CREATE
        }
        deleted_branches = {
            b
            for b in branches
            if b.state is trilium_alchemy.core.entity.types.State.DELETE
        }

        for branch_deleted in deleted_branches:
            for branch_created in created_branches:
                sorter.add(branch_deleted, branch_created)

        sorter.prepare()

        # get notes with changed child branch positions
        refresh_set = self._check_refresh(dirty_set)

        # flush entities in order provided by sorter
        while sorter.is_active():
            for entity in sorter.get_ready():
                if entity._is_dirty:
                    entity._flush(sorter)
                sorter.done(entity)

        # refresh ordering for changed branch positions
        for note in refresh_set:
            self._session.refresh_note_ordering(note)

    def add(self, entity: trilium_alchemy.core.entity.Entity) -> None:
        """
        Add provided entity to cache. Should be invoked as soon as entity_id
        is set.
        """

        if entity._entity_id in self.entity_map:
            assert entity is self.entity_map[entity._entity_id]
        else:
            self.entity_map[entity._entity_id] = entity
            logging.debug(
                f"Added to cache: entity_id={entity._entity_id}, type={type(entity)}"
            )

    def _validate(self, entity_set: set[trilium_alchemy.core.entity.Entity]):
        """
        Check all provided entities and if errors encountered, raise an
        exception with a list of errors.
        """
        errors: list[str] = []
        for entity in entity_set:
            # handle validation error
            try:
                entity._flush_check()
            except _ValidationError as e:
                errors.append(f"{entity} {type(entity)}: {e}")

        if len(errors) > 0:
            raise ValidationError(errors)

    def _flush_gather(
        self,
        entity: trilium_alchemy.core.entity.Entity,
        dirty_set: set[trilium_alchemy.core.entity.Entity],
    ):
        """
        Recursively add entity's dependencies to set if they're dirty.
        """
        for dep in entity._dependencies:
            if dep._is_dirty:
                dirty_set.add(dep)
                self._flush_gather(dep, dirty_set)

    def _check_refresh(
        self, dirty_set: set[trilium_alchemy.core.entity.Entity]
    ):
        """
        Return set of notes with changed child branch positions. These need
        to be refreshed in the UI after they're flushed.
        """

        refresh_set = set()
        for entity in dirty_set:
            if isinstance(entity, trilium_alchemy.core.branch.Branch):
                if entity._model.is_field_changed("note_position"):
                    refresh_set.add(entity.parent)

        return refresh_set

    def _summary(
        self, dirty_set: set[trilium_alchemy.core.entity.Entity]
    ) -> str:
        """
        Return a brief summary of how many entities are in each state.
        """

        def state_map():
            return {
                trilium_alchemy.core.entity.types.State.CREATE: 0,
                trilium_alchemy.core.entity.types.State.UPDATE: 0,
                trilium_alchemy.core.entity.types.State.DELETE: 0,
            }

        index = {
            trilium_alchemy.core.note.Note: state_map(),
            trilium_alchemy.core.attribute.Attribute: state_map(),
            trilium_alchemy.core.branch.Branch: state_map(),
        }

        def get_cls(entity: trilium_alchemy.core.entity.Entity):
            classes = [
                trilium_alchemy.core.note.Note,
                trilium_alchemy.core.attribute.Attribute,
                trilium_alchemy.core.branch.Branch,
            ]

            for cls in classes:
                if isinstance(entity, cls):
                    return cls

        for entity in dirty_set:
            cls = get_cls(entity)
            assert cls

            index[cls][entity._state] += 1

        notes = index[trilium_alchemy.core.note.Note]
        attributes = index[trilium_alchemy.core.attribute.Attribute]
        branches = index[trilium_alchemy.core.branch.Branch]

        # return (create/update/delete) counts
        def states(index):
            creates = index[trilium_alchemy.State.CREATE]
            updates = index[trilium_alchemy.State.UPDATE]
            deletes = index[trilium_alchemy.State.DELETE]
            return f"{creates}/{updates}/{deletes}"

        return f"{states(notes)} notes, {states(attributes)} attributes, {states(branches)} branches"
