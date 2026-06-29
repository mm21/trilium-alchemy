from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import MutableSequence, MutableSet
from pprint import pformat
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Any,
    Iterable,
    Iterator,
    Sequence,
    cast,
    overload,
)

from trilium_client.models.note import Note as EtapiNoteModel
from typecraft import validate

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
        return cast(Note, self._entity)


class NoteStatefulExtension(StatefulExtension[EtapiNoteModel], NoteExtension):
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

    def _bind_entity(self, entity: EntityT, /):
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

    def _resolve_changes(self, prev: set[EntityT], new: set[EntityT]):
        """
        Compare entity collections and ensure changed entities are in correct state.
        """
        # get sets of created/deleted entities
        created = new - prev
        deleted = prev - new

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

    def _normalize(self, obj: Any, /) -> EntityT:
        """
        Default normalizer to be overridden if necessary.

        Invoked if an entity whose class doesn't match self._child_cls is bound.
        """
        raise NotImplementedError(
            f"No normalizer defined for {type(self)}, but required to handle {obj}"
        )


class BaseEntityList[EntityT: OrderedEntity](
    BaseEntityCollection[EntityT], MutableSequence[EntityT]
):
    """
    Maintain list of entities bound to a note.

    Used for OwnedAttributes and ChildBranches.
    """

    _entity_list: list[EntityT] | None = None
    """
    Working list of entity objects, or None if not currently setup.
    """

    def __str__(self) -> str:
        return (
            f"List: {None if self._entity_list is None else pformat(self._entity_list)}"
        )

    def __len__(self) -> int:
        return len(self._norm_entity_list)

    @overload
    def __getitem__(self, i: int) -> EntityT: ...

    @overload
    def __getitem__(self, i: slice) -> list[EntityT]: ...

    def __getitem__(self, i: int | slice) -> EntityT | list[EntityT]:
        return self._norm_entity_list[i]

    @overload
    def __setitem__(self, i: int, value: EntityT): ...

    @overload
    def __setitem__(self, i: slice, value: Iterable[EntityT]): ...

    def __setitem__(self, i: int | slice, value: EntityT | Iterable[EntityT]):
        s: slice
        v: Iterable[EntityT]

        if isinstance(i, int):
            s = slice(i, i + 1)
            v = [validate(value, self._child_cls)]
        else:
            assert isinstance(value, Iterable)
            s = i
            v = [validate(v, self._child_cls) for v in value]

        # get previous entities at slice and set new ones
        prev_entity_list = self._norm_entity_list[s]
        self._norm_entity_list[s] = v

        self._resolve_changes(set(prev_entity_list), set(v))
        self._set_positions()
        self._validate()

    @overload
    def __delitem__(self, i: int): ...

    @overload
    def __delitem__(self, i: slice): ...

    def __delitem__(self, i: int | slice):
        s = i if isinstance(i, slice) else slice(i, i + 1)

        del_entities = self._norm_entity_list[s]
        del self._norm_entity_list[s]

        [self._unbind_entity(entity) for entity in del_entities]
        self._set_positions()
        self._validate()

    def __iter__(self) -> Iterator[EntityT]:
        return iter(self._norm_entity_list)

    def insert(self, index: int, value: EntityT):
        _ = validate(value, self._child_cls)
        self._norm_entity_list.insert(index, value)
        self._bind_entity(value)
        self._set_positions(index)
        self._validate()

    @property
    def _norm_entity_list(self) -> list[EntityT]:
        """
        Accessor for entity list, ensuring it was initialized.
        """
        assert self._entity_list is not None
        return self._entity_list

    def _contains(self, entity: EntityT) -> bool:
        return entity in self._norm_entity_list

    def _validate(self):
        """
        Ensure list is in a valid state.
        """
        entity_set: set[EntityT] = set()
        entity: EntityT
        prev_position: int = -1
        for entity in self._norm_entity_list:
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

    def _setattr(self, obj: Sequence[EntityT]):
        """
        Invoked when set by user.
        """
        if self is obj:
            return

        new_list = [e for e in obj]
        prev_entity_list = self._norm_entity_list
        self._entity_list = new_list

        self._resolve_changes(set(prev_entity_list), set(new_list))
        self._set_positions()
        self._validate()

    def _teardown(self):
        self._entity_list = None

    def _get_position(self, index: int) -> int:
        """
        Get position for the provided index.
        """
        if index > 0:
            # if not first, get position from index before it
            prev_position = self._norm_entity_list[index - 1]._position
        else:
            # if first, start from 10
            prev_position = 0

        return prev_position + 10

    def _set_positions(self, index: int = 0, cleanup: bool = False):
        """
        Assign positions starting with provided index.
        """
        entity_list = self._norm_entity_list
        for i in range(index, len(entity_list)):
            current_position = entity_list[i]._position
            prev_position = entity_list[i - 1]._position if i > 0 else None
            next_position = (
                entity_list[i + 1]._position if i < len(entity_list) - 1 else None
            )

            needs_update = (
                prev_position is not None and current_position <= prev_position
            ) or (next_position is not None and current_position >= next_position)

            if needs_update or cleanup or self._entity._force_position_cleanup:
                entity_list[i]._position = self._get_position(i)


class BaseEntitySet[EntityT: BaseEntity](
    BaseEntityCollection[EntityT], MutableSet[EntityT]
):
    """
    Maintain set of entities bound to a note.

    Used for ParentBranches.     Since sets aren't ordered, it emphasizes the fact that
    there are no     position values to maintain.
    """

    _entity_set: set[EntityT] | None = None
    """
    Working set of entity objects, or None if not currently setup.
    """

    def __str__(self) -> str:
        return f"Set: {None if self._entity_set is None else pformat(self._entity_set)}"

    def __contains__(self, entity: object) -> bool:
        return entity in self._norm_entity_set

    def __iter__(self) -> Iterator[EntityT]:
        return iter(self._norm_entity_set)

    def __len__(self) -> int:
        return len(self._norm_entity_set)

    def add(self, value: EntityT):
        _ = validate(value, self._child_cls)
        self._norm_entity_set.add(value)
        self._bind_entity(value)

    def discard(self, value: EntityT):
        self._norm_entity_set.discard(value)
        self._unbind_entity(value)

    @property
    def _norm_entity_set(self) -> set[EntityT]:
        assert self._entity_set is not None
        return self._entity_set

    def _contains(self, entity: EntityT) -> bool:
        return entity in self._norm_entity_set

    def _validate(self):
        """
        Ensure set is in a valid state.
        """

    def _setattr(self, obj: AbstractSet[EntityT]):
        """
        Invoked when set by user.
        """
        if self is obj:
            return

        new_set = {e for e in obj}
        prev_entity_set = self._norm_entity_set
        self._entity_set = new_set

        # resolve changes
        self._resolve_changes(prev_entity_set, new_set)

    def _teardown(self):
        self._entity_set = None
