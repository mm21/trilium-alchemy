from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import MutableSequence, MutableSet
from functools import wraps
from pprint import pformat
from typing import TYPE_CHECKING, Any, Iterable, Iterator, overload

from ..entity.entity import BaseEntity, OrderedEntity
from ..entity.model import Extension, StatefulExtension

if TYPE_CHECKING:
    from .note import Note


class NoteExtension(Extension):
    """
    Provides ._note as an alias for ._entity.
    """

    @property
    def _note(self) -> Note:
        return self._entity


class NoteStatefulExtension(StatefulExtension, NoteExtension):
    pass


class BaseEntityCollection[EntityT: BaseEntity](NoteStatefulExtension, ABC):
    """
    Used for all entity collection types defined for Note extensions:
    - Owned attributes
    - Parent branches
    - Child branches

    This is agnostic of whether or not there is a concept of position.
    """

    # class of element of this collection
    _child_cls: type[EntityT]

    # name of attribute to associate with owner of collection
    # should be 'note_id' (attrs) or 'parent_note_id' (child branches)
    _owner_field: str

    @abstractmethod
    def _contains(self, entity: EntityT) -> bool:
        """
        Returns True if provided entity is present in this collection.
        """
        ...

    @abstractmethod
    def _validate(self):
        """
        Ensure container is in a valid state, e.g. with no duplicates.
        """
        ...

    def _bind_entity(self, entity: EntityT):
        """
        Associate provided entity with this note.
        """

        assert not entity._is_delete

        # ensure already in collection
        assert self._contains(entity)

        # ensure not bound to another note
        note = getattr(entity, self._owner_field)

        assert note in {
            self._note,
            None,
        }, f"Entity {entity} attempted to bind to {self._note} but was already bound to {note}"

        # assign note if not set
        if note is None:
            setattr(entity, self._owner_field, self._note)

    def _unbind_entity(self, entity: EntityT):
        """
        Remove provided entity from note.
        """

        # ensure not in collection
        assert not self._contains(entity)

        if not entity._is_delete:
            entity.delete()

    def _resolve_changes(self, old: set[EntityT], new: set[EntityT]):
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

    def _invoke_normalize(self, value: Any) -> EntityT:
        if not isinstance(value, self._child_cls):
            value = self._normalize(value)
            assert isinstance(
                value, self._child_cls
            ), f"{value} is not an instance of {self._child_cls}"
        return value

    def _normalize(self, value: Any) -> EntityT:
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
    def wrapper(self, new: Any):
        if self is new:
            return
        else:
            func(self, new)

    return wrapper


class BaseEntityList[EntityT: OrderedEntity](
    BaseEntityCollection[EntityT], MutableSequence[EntityT]
):
    """
    Maintain list of entities bound to a note. Used for OwnedAttributes and
    ChildBranches.
    """

    _entity_list: list[EntityT] | None = None
    """
    Working list of entity objects, or None if not currently setup.
    """

    def __str__(self) -> str:
        return f"List: {None if self._entity_list is None else pformat(self._entity_list)}"

    def __len__(self) -> int:
        assert self._entity_list is not None
        return len(self._entity_list)

    @overload
    def __getitem__(self, i: int) -> EntityT:
        ...

    @overload
    def __getitem__(self, i: slice) -> list[EntityT]:
        ...

    def __getitem__(self, i: int | slice) -> EntityT | list[EntityT]:
        assert self._entity_list is not None
        return self._entity_list[i]

    @overload
    def __setitem__(self, i: int, value: EntityT):
        ...

    @overload
    def __setitem__(self, i: slice, value: Iterable[EntityT]):
        ...

    def __setitem__(self, i: int | slice, value: EntityT | Iterable[EntityT]):
        assert self._entity_list is not None

        s: slice
        v: Iterable[EntityT]

        if isinstance(i, slice):
            s = i
            v = [self._invoke_normalize(v) for v in value]
        else:
            s = slice(i, i + 1)
            v = [self._invoke_normalize(value)]

        # get previous entities at slice and set new ones
        entities_del: Iterable[EntityT] = self._entity_list[s]
        self._entity_list[s] = v

        self._resolve_changes(set(entities_del), set(v))
        self._set_positions()
        self._validate()

    @overload
    def __delitem__(self, i: int):
        ...

    @overload
    def __delitem__(self, i: slice):
        ...

    def __delitem__(self, i: int | slice):
        assert self._entity_list is not None

        s: slice = i if isinstance(i, slice) else slice(i, i + 1)

        entities_del = self._entity_list[s]
        del self._entity_list[s]

        [self._unbind_entity(entity) for entity in entities_del]
        self._set_positions()
        self._validate()

    def __iter__(self) -> Iterator[EntityT]:
        return iter(self._entity_list)

    def insert(self, i: int, value: EntityT):
        assert self._entity_list is not None

        entity: EntityT = self._invoke_normalize(value)
        self._entity_list.insert(i, entity)

        self._bind_entity(entity)
        self._set_positions(i)
        self._validate()

    def _contains(self, entity: EntityT) -> bool:
        assert self._entity_list is not None
        return entity in self._entity_list

    def _validate(self):
        """
        Ensure list is in a valid state.
        """

        assert self._entity_list is not None

        entity_set: set[EntityT] = set()
        entity: EntityT
        prev_position: int = -1
        for entity in self._entity_list:
            # ensure entity hasn't been seen before
            assert (
                entity not in entity_set
            ), f"Entity {entity} has multiple occurrences in list owned by {self._note}"

            # ensure positions are consistent
            assert (
                entity._position > prev_position
            ), f"Entity {entity} has position {entity._position} <= previous entity {prev_position}; possibly already placed in list owned by {self._note}"

            entity_set.add(entity)
            prev_position = entity._position

    @check_bailout
    def _setattr(self, new_list: list[EntityT]):
        """
        Invoked when set by user.
        """
        assert self._entity_list is not None

        # normalize list
        normalized_list: list[EntityT] = [
            self._invoke_normalize(entity) for entity in new_list
        ]

        # assign new list
        entity_list_prev = self._entity_list
        self._entity_list = normalized_list

        self._resolve_changes(set(entity_list_prev), set(normalized_list))
        self._set_positions()
        self._validate()

    def _teardown(self):
        self._entity_list = None

    def _get_position(self, index: int) -> int:
        """
        Get position for the provided index.
        """
        assert self._entity_list is not None

        if index > 0:
            # if not first, get position from index before it
            prev_position = self._entity_list[index - 1]._position
        else:
            # if first, start from 10
            prev_position = 0

        return prev_position + 10

    def _set_positions(self, index: int = 0, cleanup: bool = False):
        """
        Assign positions starting with provided index.
        """
        assert self._entity_list is not None

        for i in range(index, len(self._entity_list)):
            current_position = self._entity_list[i]._position
            prev_position = (
                self._entity_list[i - 1]._position if i > 0 else None
            )
            next_position = (
                self._entity_list[i + 1]._position
                if i < len(self._entity_list) - 1
                else None
            )

            needs_update = (
                prev_position is not None and current_position <= prev_position
            ) or (
                next_position is not None and current_position >= next_position
            )

            if needs_update or cleanup or self._entity._force_position_cleanup:
                self._entity_list[i]._position = self._get_position(i)


class BaseEntitySet[EntityT: BaseEntity](
    BaseEntityCollection[EntityT], MutableSet[EntityT]
):
    """
    Maintain set of entities bound to a note. Used for ParentBranches.

    Since sets aren't ordered, it emphasizes the fact that there are no
    position values to maintain.
    """

    _entity_set: set[EntityT] | None = None
    """
    Working set of entity objects, or None if not currently setup.
    """

    def __str__(self) -> str:
        return f"Set: {None if self._entity_set is None else pformat(self._entity_set)}"

    def __contains__(self, entity: EntityT) -> bool:
        assert self._entity_set is not None
        return entity in self._entity_set

    def __iter__(self) -> Iterator[EntityT]:
        assert self._entity_set is not None
        return iter(self._entity_set)

    def __len__(self) -> int:
        assert self._entity_set is not None
        return len(self._entity_set)

    def add(self, value: EntityT):
        assert self._entity_set is not None

        entity: EntityT = self._invoke_normalize(value)
        self._entity_set.add(entity)
        self._bind_entity(entity)

    def discard(self, value: EntityT):
        assert self._entity_set is not None

        entity: EntityT = self._invoke_normalize(value)
        self._entity_set.discard(entity)
        self._unbind_entity(entity)

    def _contains(self, entity: EntityT) -> bool:
        assert self._entity_set is not None
        return entity in self._entity_set

    def _validate(self):
        """
        Ensure set is in a valid state.
        """

    @check_bailout
    def _setattr(self, new_set: set[EntityT]):
        """
        Invoked when set by user.
        """
        assert self._entity_set is not None

        # normalize set
        normalized_set: set[EntityT] = {
            self._invoke_normalize(entity) for entity in new_set
        }

        # assign new set
        entity_set_prev = self._entity_set
        self._entity_set = normalized_set

        # resolve changes
        self._resolve_changes(entity_set_prev, normalized_set)

    def _teardown(self):
        self._entity_set = None
