from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from graphlib import TopologicalSorter
from typing import Any, Generator, Self, cast, overload

from pydantic import BaseModel
from trilium_client.exceptions import ApiException, NotFoundException

from ..exceptions import *
from ..session import Session, SessionContainer, normalize_session
from .model import (
    BaseEntityModel,
    FieldDescriptor,
    ModelContainer,
    WriteOnceDescriptor,
    WriteThroughDescriptor,
)
from .types import State

__all__ = [
    "BaseEntity",
    "State",
    "EntityIdDescriptor",
    "FieldDescriptor",
    "WriteThroughDescriptor",
    "WriteOnceDescriptor",
]

__rollup__ = [
    "BaseEntity",
    "State",
]


class BaseEntity[ModelT: BaseEntityModel](
    ABC, SessionContainer, ModelContainer
):
    """
    Base class for Trilium entities.

    Should not be instantiated by user, but published for reference.
    """

    # unique id
    _entity_id: str | None = None

    # init state
    _init_done: bool = False

    # current state
    _state: State

    # type used to create _model
    _model_cls: type[ModelT]

    _force_position_cleanup: bool = False

    def __new__(
        cls,
        # entity id, or None to create new one
        entity_id: str | None = None,
        # session, or None to use default session
        session: Session | None = None,
        # backing model, if already loaded
        model_backing: ModelT | None = None,
        # whether entity is being created (otherwise inferred from whether
        # entity_id provided)
        create: bool | None = None,
    ) -> Self:
        session = normalize_session(session)
        # check if this object is already cached
        if entity_id is not None and entity_id in session._cache.entity_map:
            entity = session._cache.entity_map[entity_id]

            # sanity check: cached object can be subclass or superclass
            # enables equivalency of declarative definitions, e.g.:
            # Note(note_id='root') and Root()
            assert isinstance(entity, cls) or issubclass(cls, type(entity))

            if cls is not type(entity) and issubclass(cls, type(entity)):
                # initializing a subclassed Note which is already cached. reset
                # init state and reassign class to trigger initializing it as
                # expected.
                entity._init_done = False
                entity.__class__ = cls

            # return cached object
            return entity
        # proceed with creation of new object
        return super().__new__(cls)

    def __init__(
        self,
        *,
        entity_id: str | None = None,
        session: Session | None = None,
        model_backing: ModelT | None = None,
        create: bool | None = None,
    ):
        session = normalize_session(session)

        # skip init if already done, but update model if needed
        if self._init_done:
            assert self._entity_id == entity_id
            assert (
                self._session is session
            ), f"Attempt to associate new session {session} with entity having existing session {self._session}"

            self._model.setup_check_init(model_backing)
            return

        # set early since if this is a declarative note, it may create children
        # which instantiate it (set as target of relation)
        self._init_done = True

        self._state = State.CLEAN
        SessionContainer.__init__(self, session)
        ModelContainer.__init__(self, self._model_cls(self))

        if entity_id is None:
            # set create flag if no entity_id provided
            create = True
        else:
            # set entity_id and add to cache
            self._set_entity_id(entity_id)

        # invoke subclassed init hook (model extensions, etc)
        self._init()

        # setup model if needed
        self._model.setup_check_init(model_backing, create)

    def __str__(self):
        return self.str_short

    def __repr__(self):
        return str(self)

    @classmethod
    @abstractmethod
    def _from_id(self, entity_id: str, session: Session = None):
        """
        Instantiate this entity from an id.
        """
        ...

    @classmethod
    @abstractmethod
    def _from_model(self, model: BaseModel):
        ...

    @property
    def state(self) -> State:
        """
        Current state.
        """
        return self._state

    @property
    def session(self) -> Session:
        """
        Session to which this entity belongs.
        """
        return self._session

    @property
    def str_short(self) -> str:
        """
        Get a short description of this entity.
        """
        # don't directly subclass this so it's shown next to str_summary
        # in docs
        return self._str_short

    @property
    def str_summary(self) -> str:
        """
        Get a summary of this entity, including its current state and model
        values.
        """
        indent = f"\n{' '*4}"
        return indent.join(
            [self.str_short]
            + self._str_summary_extra_pre
            + [str(self._state), str(self._model)]
            + self._str_summary_extra_post
        )

    @property
    def _str_summary_extra_pre(self) -> list[str]:
        """
        Get extra lines to be inserted at beginning of summary.
        """
        return []

    @property
    def _str_summary_extra_post(self) -> list[str]:
        """
        Get extra lines to be inserted at end of summary.
        """
        return []

    @property
    @abstractmethod
    def _str_short(self):
        """
        Implementation of str_short so as to keep it next to str_summary
        in docs.
        """
        ...

    @property
    @abstractmethod
    def _str_safe(self):
        """
        Return string for debugging and don't invoke model setup.
        """
        ...

    @property
    def _is_clean(self) -> bool:
        return self._state is State.CLEAN

    @property
    def _is_dirty(self) -> bool:
        return self._state is not State.CLEAN

    @property
    def _is_create(self) -> bool:
        return self._state is State.CREATE

    @property
    def _is_update(self) -> bool:
        return self._state is State.UPDATE

    @property
    def _is_delete(self) -> bool:
        return self._state is State.DELETE

    @property
    def _is_abandoned(self) -> bool:
        return (
            self._state in {State.CLEAN, State.DELETE} and self._model._nexists
        )

    @property
    def _is_orphan(self) -> bool:
        return any(
            dep._is_abandoned or dep._is_delete for dep in self._dependencies
        )

    def flush(self):
        """
        Commit changes to Trilium for this entity and its dependencies.
        """
        self._session._cache.flush({self})

    def invalidate(self):
        """
        Discard cached contents and user-provided data for this object.
        Upon next access, data will be fetched from Trilium.
        """
        for entity in [self] + self._associated_entities:
            entity._model.teardown()
            if entity._is_dirty:
                entity._set_clean()

    def delete(self):
        """
        Mark this entity for pending delete.
        """
        self._delete()

    def refresh(self):
        """
        Update value from Trilium, discarding any local changes.
        """
        self.invalidate()
        self._model.setup()

    def _delete(self):
        """
        Use wrapper so delete() is listed in a consistent order when
        _delete() is subclassed.
        """
        self._model.setup_check()
        self._set_dirty(State.DELETE)

    def _set_attrs(self, **kwargs):
        for attr, val in kwargs.items():
            if val is not None:
                # set attribute on self
                setattr(self, attr, val)

    def _set_entity_id(self, entity_id: str):
        """
        Set entity id and add to cache.
        """
        assert entity_id is not None

        if self._entity_id is None:
            self._entity_id = entity_id
            self._session._cache.add(self)
        else:
            assert self._entity_id == entity_id

    def _refresh_model(self, model: BaseModel):
        """
        Discard current model and update with new one.
        """
        self.invalidate()
        self._model.setup(model_backing=model, create=False)

    def _flush(self, sorter: TopologicalSorter):
        """
        Commit changes to Trilium database for this object.
        """

        self.session._logger.debug(f"Flushing: {self.str_summary}")

        model_new: BaseModel | None = None
        gen: Generator | None = None

        assert self._is_dirty

        if self._is_abandoned:
            # bail out if deleting an entity which never got created
            pass
        elif self._is_orphan:
            # bail out if a dependency was abandoned
            # TODO: specify which dependency was abandoned
            self.session._logger.warning(
                f"Orphaned entity not being flushed since a dependency was abandoned: {self.str_summary}"
            )
        else:
            try:
                # flush model if it has pending changes
                if (
                    self._state in {State.CREATE, State.DELETE}
                    or self._model.fields_changed
                ):
                    model_new, gen = self._model.flush(sorter)
            except (NotFoundException, ApiException) as e:
                self.session._logger.warning(
                    f"Flush failed, likely implicitly deleted by another operation: {self.str_summary} ({type(e).__name__})"
                )
            else:
                if self._state is not State.DELETE:
                    # get latest model from extensions if applicable
                    model_new = self._model.flush_extensions() or model_new

        # mark as clean
        self._set_clean()

        # perform setup if we got a new model
        if model_new is not None:
            self._model.setup(model_new)

        # continue flush sequence, if needed by subclass
        if gen is not None:
            try:
                next(gen)
            except StopIteration:
                pass

    def _check_state(self):
        """
        Invoked upon field update by user.
        """

        # handle dirty state based on entity state
        if self._state is State.CLEAN:
            # compare model fields valid for update and set dirty if different
            if self._model.is_changed:
                self._set_dirty(State.UPDATE)

        elif self._state is State.CREATE:
            # do nothing; should already be in dirty set
            assert self in self._session._cache.dirty_set

        elif self._state is State.UPDATE:
            # compare models and set clean if same
            if self._model.is_changed is False:
                self._set_clean()

        else:
            raise Exception(f"Entity in invalid state: {self._state}")

    def _set_clean(self):
        """
        Set as clean from dirty state.
        """
        assert self._is_dirty
        assert self in self._session._cache.dirty_set

        self._state = State.CLEAN
        self._session._cache.dirty_set.remove(self)

    def _set_dirty(self, state: State):
        """
        Set as dirty in requested state.
        """
        assert state is not State.CLEAN

        # check if not already in requested state
        if not self._state is state:
            if self._is_clean:
                # clean -> dirty transition: add to dirty set
                assert (
                    self not in self._session._cache.dirty_set
                ), f"Already in dirty_set with state {self.state}: {self}"
                self._session._cache.dirty_set.add(self)
            else:
                # dirty -> dirty transition: make sure already in dirty set
                assert self in self._session._cache.dirty_set

                if self._is_create:
                    # only create -> delete allowed
                    assert state is State.DELETE

                elif self._is_update:
                    # update -> create not allowed
                    assert state is not State.CREATE

            self._state = state

    # --------------------------------------------------------------------------
    # To be implemented by subclass
    # --------------------------------------------------------------------------

    def _init(self):
        """
        Register model extensions or any other init needed before model setup.
        """
        ...

    def _setup(self, model: ModelT | None):
        """
        Populate fields based on model retrieved from database.
        """
        ...

    @abstractmethod
    def _flush_check(self):
        """
        Check if this object is in a valid state to be committed to database.

        Upon invalid state, should raise AssertionError with useful
        description of problem.
        """
        ...

    def _flush_prep(self):
        """
        Propagate any values to fields if needed before flush.
        """
        ...

    @property
    @abstractmethod
    def _dependencies(self) -> set[BaseEntity]:
        """
        Return entities this entity depends on.
        """
        ...

    @property
    def _associated_entities(self) -> list[BaseEntity]:
        """
        Return entities to be refreshed/cleaned up along with this one.
        """
        return []


class PositionMixin:
    """
    Mixin to indicate that an Entity subclass has a position field.
    """

    _position: int


# TODO: this is better suited as an intersection type, not yet supported
# - https://github.com/python/typing/issues/213
# - https://github.com/CarliJoy/intersection_examples/issues/8
class OrderedEntity[ModelT: BaseEntityModel](BaseEntity[ModelT], PositionMixin):
    pass


class EntityIdDescriptor:
    """
    Accessor for read-only entity id.

    :raises ReadOnlyError: Upon write attempt
    """

    @overload
    def __get__(self, ent: None, objtype: None) -> EntityIdDescriptor:
        ...

    @overload
    def __get__(self, ent: BaseEntity, objtype: type[BaseEntity]) -> str:
        ...

    def __get__(
        self,
        ent: BaseEntity | None,
        objtype: type[BaseEntity] | None = None,
    ) -> EntityIdDescriptor | str:
        if ent is None:
            return self
        return cast(str, ent._entity_id)

    def __set__(self, ent: BaseEntity, val: Any):
        raise ReadOnlyError("_entity_id", ent)


def normalize_entities[
    CollectionT: Iterable
](
    entities: BaseEntity | tuple | Iterable[BaseEntity | tuple],
    collection_cls: type[CollectionT] = list,
) -> CollectionT:
    """
    Take an entity or iterable of entities and return an iterable.
    Also supports tuples, e.g. (child, "prefix")
    """

    if (
        isinstance(entities, Iterable)
        and not isinstance(entities, tuple)
        and not isinstance(entities, BaseEntity)
    ):
        # have iterable
        return collection_cls(entities)

    # have single entity
    return collection_cls([entities])
