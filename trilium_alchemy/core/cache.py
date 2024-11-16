"""
Implements a cache of Trilium entities.
"""

from __future__ import annotations

import graphlib
import logging
from typing import TYPE_CHECKING, Iterable

from .exceptions import ValidationError, _ValidationError

if TYPE_CHECKING:
    from .entity import BaseEntity
    from .session import Session


class Cache:
    """
    Combines a cache and unit of work collection. Maintains changes made by user
    and synchronizes with Trilium upon flush.
    """

    entity_map: dict[str, BaseEntity]
    """Mapping of entity id to entity object"""

    dirty_set: set[BaseEntity]
    """Set of objects which need to be synchronized with Trilium"""

    _session: Session

    def __init__(self, session: Session):
        self._session = session
        self.entity_map = dict()
        self.dirty_set = set()

    def __str__(self):
        return (
            f"Cache: entity_map={self.entity_map}, dirty_set={self.dirty_set}"
        )

    def flush(
        self,
        entities: Iterable[BaseEntity] | None = None,
    ):
        """
        Flushes provided entities and all dependencies, or all dirty entities
        if entities not provided.
        """
        from .branch import Branch
        from .entity.types import State

        entities_iter: Iterable[BaseEntity]

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

        logging.debug(
            f"Flushing {len(dirty_set)} entities: (create/update/delete) {self._summary(dirty_set)}"
        )

        # create topological sorter
        sorter = graphlib.TopologicalSorter()

        # populate and prepare sorter
        for entity in dirty_set:
            sorter.add(entity)

            for dep in entity._dependencies:
                if dep._is_dirty:
                    sorter.add(entity, dep)

        # add dependency of all deleted branches on all created
        # branches. this avoids any notes being accidentally
        # deleted by an ancestor being deleted
        branches = {b for b in dirty_set if isinstance(b, Branch)}
        created_branches = {b for b in branches if b.state is State.CREATE}
        deleted_branches = {b for b in branches if b.state is State.DELETE}

        for branch_deleted in deleted_branches:
            for branch_created in created_branches:
                sorter.add(branch_deleted, branch_created)

        sorter.prepare()

        # get notes with changed child branch positions
        refresh_set = self._check_refresh(dirty_set)

        # flush entities in order provided by sorter
        while sorter.is_active():
            ready: list[BaseEntity] = list(sorter.get_ready())

            for entity in ready:
                if entity._is_dirty:
                    do_cleanup = entity._is_delete
                    entity._flush(sorter)

                    # remove entity and associated entities from map
                    if do_cleanup:
                        for e in [entity] + entity._associated_entities:
                            if e._entity_id in self.entity_map:
                                del self.entity_map[e._entity_id]

                sorter.done(entity)

        # refresh ordering for changed branch positions
        for note in refresh_set:
            self._session.refresh_note_ordering(note)

    def add(self, entity: BaseEntity):
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

    def _validate(self, entity_set: set[BaseEntity]):
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
        entity: BaseEntity,
        dirty_set: set[BaseEntity],
    ):
        """
        Recursively add entity's dependencies to set if they're dirty.
        """
        for dep in entity._dependencies:
            if dep._is_dirty:
                dirty_set.add(dep)
                self._flush_gather(dep, dirty_set)

    def _check_refresh(self, dirty_set: set[BaseEntity]):
        """
        Return set of notes with changed child branch positions. These need
        to be refreshed in the UI after they're flushed.
        """

        from .branch import Branch

        refresh_set = set()
        for entity in dirty_set:
            if isinstance(entity, Branch):
                if entity._model.is_field_changed("note_position"):
                    refresh_set.add(entity.parent)

        return refresh_set

    def _summary(self, dirty_set: set[BaseEntity]) -> str:
        """
        Return a brief summary of how many entities are in each state.
        """

        from .attribute import BaseAttribute
        from .branch import Branch
        from .entity.types import State
        from .note import Note

        def state_map():
            return {
                State.CREATE: 0,
                State.UPDATE: 0,
                State.DELETE: 0,
            }

        index = {
            Note: state_map(),
            BaseAttribute: state_map(),
            Branch: state_map(),
        }

        def get_cls(entity: BaseEntity):
            classes = [
                Note,
                BaseAttribute,
                Branch,
            ]

            for cls in classes:
                if isinstance(entity, cls):
                    return cls

        for entity in dirty_set:
            cls = get_cls(entity)
            assert cls

            index[cls][entity._state] += 1

        notes = index[Note]
        attributes = index[BaseAttribute]
        branches = index[Branch]

        # return (create/update/delete) counts
        def states(index):
            creates = index[State.CREATE]
            updates = index[State.UPDATE]
            deletes = index[State.DELETE]
            return f"{creates}/{updates}/{deletes}"

        return f"{states(notes)} notes, {states(attributes)} attributes, {states(branches)} branches"
