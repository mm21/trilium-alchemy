from __future__ import annotations

from typing import overload, TypeVar, Generic, Type, Hashable, Any
from functools import wraps
from pprint import pformat

from collections.abc import MutableSequence, MutableSet, MutableMapping
from abc import ABC, abstractmethod

from trilium_client.models.note import Note as EtapiNoteModel

from ..exceptions import *
from ..entity import Entity
from ..entity.model import Extension, StatefulExtension

T = TypeVar("T", bound=Entity)


class NoteExtension(Extension):
    """
    Provides ._note as an alias for ._entity.
    """

    @property
    def _note(self):
        return self._entity


class NoteStatefulExtension(StatefulExtension, NoteExtension):
    pass


class Collection(Generic[T], NoteStatefulExtension, ABC):
    """
    Used for all entity collection types defined for Note extensions:
    - Owned attributes
    - Parent branches
    - Child branches
    """

    # class of element of this collection
    _child_cls: Type[T] = None

    # name of attribute to associate with owner of collection
    # should be 'note_id' (attrs) or 'parent_note_id' (child branches)
    _owner_field: str = None

    # TODO: property note, alias for entity

    def _bind_entity(self, entity: T):
        """
        Associate provided entity with this note.
        """

        assert not entity._is_delete

        # ensure not bound to another note
        note = getattr(entity, self._owner_field)

        assert note in {
            self._note,
            None,
        }, f"Entity {entity} attempted to bind to {self._note} but was already bound to {note}"

        # assign note if not set
        if note is None:
            setattr(entity, self._owner_field, self._note)

    def _unbind_entity(self, entity: T):
        """
        Remove provided entity from note.
        """

        # TODO: check might not be necessary anymore
        if not entity._is_delete:
            entity.delete()

    def _resolve_changes(self, old: set[T], new: set[T]):
        """
        Compare entity collections and ensure changed entities are in
        correct state.
        """

        # get sets of created/deleted entities
        created = new - old
        deleted = old - new

        # process new entities
        for entity in created:
            self._bind_entity(entity)

        # ensure removed entities are in delete state
        for entity in deleted:
            self._unbind_entity(entity)

    def _invoke_normalize(self, value: Any):
        if not isinstance(value, self._child_cls):
            value = self._normalize(value)
            assert isinstance(
                value, self._child_cls
            ), f"{value} is not {self._child_cls}"
        return value

    def _normalize(self, value: Any):
        """
        Default normalizer to be overridden if necessary. Invoked if
        an entity whose class doesn't match self._child_cls is bound.
        """
        raise NotImplementedError(
            f"No normalizer defined for {type(self)}, but required to handle {value}"
        )


def check_bailout(func):
    """
    Bail out if assigning to self (gets called for __iadd__ helpers)
    - This works fine without early bailout, but adds overhead
    """

    @wraps(func)
    def _check_bailout(self, new: Any):
        if self is new:
            return
        else:
            func(self, new)

    return _check_bailout


class List(Collection[T], MutableSequence):
    """
    Maintain list of entities bound to a note. Used for OwnedAttributes and
    ChildBranches.
    """

    # working list of entity objects
    _entity_list: list[T] = None

    def __str__(self):
        return f"List: {None if self._entity_list is None else pformat(self._entity_list)}"

    # invoked when set by user
    @check_bailout
    def _setattr(self, new_list: list[Any]):
        normalized_list: list[T] = list()

        # normalize list
        for value in new_list:
            entity = self._invoke_normalize(value)
            normalized_list.append(entity)

        # assign new list
        entity_list = self._entity_list
        self._entity_list = normalized_list

        # recalculate positions
        self._reorder()

        # resolve changes between new list and current list
        self._resolve_changes(set(entity_list), set(normalized_list))

    def _teardown(self):
        self._entity_list = None

    def __len__(self):
        return len(self._entity_list)

    def __getitem__(self, i: int):
        return self._entity_list[i]

    def __setitem__(self, i: int, value: Any):
        entity: T = self._invoke_normalize(value)

        # check if entity is already at this index
        if entity is self._entity_list[i]:
            return

        # delete previous entity at this index and add new one
        entity_del = self._entity_list[i]
        self._entity_list[i] = entity
        entity_del.delete()

        # set position to previous entity's position and bind to self
        self._entity_list[i]._position = entity_del.position
        self._bind_entity(entity)

        # TODO: reusable sanity check: entity's position is between
        # entities before/after in list

    def __delitem__(self, i: int):
        # delete entity at provided index
        entity_del = self._entity_list[i]
        del self._entity_list[i]
        self._unbind_entity(entity_del)

        # re-calculate positions
        self._reorder(i)

    def insert(self, i: int, value: Any):
        entity: T = self._invoke_normalize(value)

        self._entity_list.insert(i, entity)
        self._bind_entity(entity)
        self._reorder(i)

    # get position for provided index
    def _get_position(self, index: int, base: int = 0) -> int:
        if index > 0:
            # if not first, get position from index before it
            position_prev = self._entity_list[index - 1]._position
        else:
            # if first, get position as base + 10
            position_prev = base

        return position_prev + 10

    # assign positions starting with provided index
    # assumes position is a valid attribute of entity
    # (i.e. only attributes and branches)
    def _reorder(self, index: int = 0):
        for i in range(index, len(self._entity_list)):
            self._entity_list[i]._position = self._get_position(i)


class Set(Collection[T], MutableSet):
    """
    Maintain set of entities bound to a note. Used for ParentBranches.

    Since sets aren't ordered, it emphasizes the fact that there are no
    position values to maintain.
    """

    # working set of entity objects
    _entity_set: set[T] = None

    def __str__(self):
        return f"Set: {None if self._entity_set is None else pformat(self._entity_set)}"

    # invoked when set by user
    @check_bailout
    def _setattr(self, new_set: set[Any]):
        normalized_set: set[T] = set()

        # normalize set
        for value in new_set:
            entity = self._invoke_normalize(value)
            normalized_set.add(entity)

        # resolve changes between new set and old set
        self._resolve_changes(self._entity_set, normalized_set)

        # assign new set
        self._entity_set = normalized_set

    def _teardown(self):
        self._entity_set = None

    def __contains__(self, entity: T):
        return entity in self._entity_set

    def __iter__(self):
        yield from self._entity_set

    def __len__(self):
        return len(self._entity_set)

    def add(self, value: Any):
        entity: T = self._invoke_normalize(value)
        self._entity_set.add(entity)
        self._bind_entity(entity)

    def discard(self, value: Any):
        entity: T = self._invoke_normalize(value)
        self._entity_set.discard(entity)
        self._unbind_entity(entity)
