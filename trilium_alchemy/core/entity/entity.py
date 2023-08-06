from __future__ import annotations

from typing import overload, TypeVar, Generic, Type, Any, Generator
from abc import ABC, ABCMeta, abstractmethod
from graphlib import TopologicalSorter
import inspect
import logging

from pydantic import BaseModel

from trilium_client.exceptions import NotFoundException, ApiException

from .model import (
    Model,
    ModelContainer,
    FieldDescriptor,
    ReadOnlyFieldDescriptor,
    ReadOnlyDescriptor,
    WriteThroughDescriptor,
    WriteOnceDescriptor,
    ExtensionDescriptor,
)
from .types import State
from ..exceptions import *
from ..session import Session, require_session

import trilium_alchemy

__all__ = [
    "Entity",
    "State",
    "EntityIdDescriptor",
    "FieldDescriptor",
    "ReadOnlyFieldDescriptor",
    "ReadOnlyDescriptor",
    "WriteThroughDescriptor",
    "WriteOnceDescriptor",
    "ExtensionDescriptor",
]

__rollup__ = [
    "Entity",
    "State",
]

ModelT = TypeVar("ModelT", bound=Model)


class Entity(Generic[ModelT], ABC, ModelContainer):
    """
    Base class for Trilium entities.

    Should not be instantiated by user, but published for reference.
    """

    # unique id
    # TODO: use WriteOnceDescriptor subclass with automatic invocation
    # of session._cache.add()
    _entity_id: str = None

    # init state
    _init_done: bool = False

    # session for access to API and cache
    _session: Session = None

    # current state
    _state: State = None

    # type used to create _model
    _model_cls: Type[ModelT] = None

    @require_session
    def __new__(
        cls,
        # entity id, or None to create new one
        entity_id: str | None = None,
        # session, or None to use default session (populated by require_session)
        session: Session = None,
        # backing model, if already loaded
        model_backing: ModelT | None = None,
        # whether entity is being created (otherwise inferred from whether
        # entity_id provided)
        create: bool | None = None,
    ):
        # check if this object is already cached
        if entity_id is not None and entity_id in session._cache.entity_map:
            entity = session._cache.entity_map[entity_id]

            # sanity check: cached object can be subclass or superclass
            # enables equivalency of declarative definitions, e.g.:
            # Note(note_id='root') and Root()
            # TODO: check if cls extends existing entity and set __class__ if so
            assert isinstance(entity, cls) or issubclass(cls, type(entity))

            if cls is not type(entity) and issubclass(cls, type(entity)):
                # initializing a subclassed Note which is already cached. reset
                # init state and reassign class to trigger initializing it as
                # expected.
                entity._init_done = False
                entity.__class__ = cls

            # return cached object
            return entity
        else:
            # proceed with creation of new object
            return super().__new__(cls)

    @require_session
    def __init__(
        self,
        entity_id: str | None = None,
        session: Session = None,
        model_backing: ModelT | None = None,
        create: bool | None = None,
    ):
        # skip init if already done, but update model if needed
        if self._init_done:
            assert self._entity_id == entity_id
            assert (
                self._session is session
            ), "Attempt to associate new session {session} with entity having existing session {self._session}"

            self._model.setup_check_init(model_backing)
            return

        # set early since if this is a declarative note, it may create children
        # which instantiate it (set as target of relation)
        self._init_done = True

        ModelContainer.__init__(self, self._model_cls(self))
        self._session = session
        self._state = State.CLEAN

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
        return f"{self.str_short} <{self._state}> {self._model}"

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

    def flush(self) -> None:
        """
        Commit changes to Trilium for this entity and its dependencies.
        """
        self._session._cache.flush({self})

    # TODO: override by Note to include attributes and branches?
    # TODO: if create, don't allow invalidate or act as alias for delete?
    def invalidate(self) -> None:
        """
        Discard cached contents and user-provided data for this object.
        Upon next access, data will be fetched from Trilium.
        """
        self._model.teardown()
        if self._is_dirty:
            self._set_clean()

    def delete(self) -> None:
        """
        Mark this entity for pending delete.
        """
        self._delete()

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

    # TODO: use subclassed WriteOnceDescriptor to also add to cache
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

    # TODO: owned by model
    def _refresh_model(self, model: BaseModel):
        """
        Discard current model and update with new one.
        """
        # TODO: invalidate note recursively
        self.invalidate()
        self._model.setup(model_backing=model, create=False)

    # TODO: owned by model, subclass for etapi/filesystem
    def _flush_model(
        self, sorter: TopologicalSorter
    ) -> tuple[BaseModel | None, Generator | None]:
        """
        Flush model if any fields are changed.
        """

        if self._state in [State.CREATE, State.UPDATE]:
            # if creating or updating, invoke flush prep
            self._flush_prep()

        # get flush method based on state
        func = {
            State.CREATE: self._flush_create,
            State.UPDATE: self._flush_update,
            State.DELETE: self._flush_delete,
        }[self._state]

        # invoke flush method
        model_new: BaseModel | None
        if inspect.isgeneratorfunction(func):
            # generator function: yields model, then performs extra processing
            gen = func(sorter)
            model_new = next(gen)
        else:
            # not generator function: just returns model
            gen = None
            model_new = func(sorter)

        # ensure we got the updated model
        if self._state in [State.CREATE, State.UPDATE]:
            assert model_new is not None
        else:
            assert model_new is None

        if self._state is State.CREATE:
            # set entity id if needed
            if self._entity_id is None:
                entity_id = getattr(model_new, self._model.field_entity_id)
                self._set_entity_id(entity_id)

        return (model_new, gen)

    def _flush(self, sorter: TopologicalSorter) -> None:
        """
        Commit changes to Trilium database for this object.
        """

        logging.debug(f"Flushing: {self.str_summary}")

        model_new: BaseModel | None = None
        gen: Generator | None = None

        if (
            self._state in {State.CREATE, State.DELETE}
            or self._model.fields_changed
        ):
            # bail out if deleting an entity which never got created
            if self._is_abandoned:
                pass
            elif self._is_orphan:
                # TODO: specify which dependency was abandoned
                logging.warning(
                    f"Orphaned entity not being flushed since a dependency was abandoned: {self.str_summary}"
                )
                pass
            else:
                try:
                    model_new, gen = self._flush_model(sorter)
                except (NotFoundException, ApiException) as e:
                    logging.warning(
                        f"Flush failed, likely implicitly deleted by another operation: {self.str_summary} ({type(e).__name__})"
                    )

        if self._state is not State.DELETE and self._model.extension_changed:
            self._model.flush_extensions()

        # mark as clean
        self._set_clean()

        # perform setup if model is newer
        if model_new is not None and self._model.check_newer(model_new):
            self._model.setup(model_new)

        # continue flush sequence, if needed by subclass
        if gen is not None:
            try:
                next(gen)
            except StopIteration as e:
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

    def _init(self) -> None:
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
    def _flush_check(self) -> None:
        """
        Check if this object is in a valid state to be committed to database.

        Upon invalid state, should raise AssertionError with useful
        description of problem.
        """
        ...

    @abstractmethod
    def _flush_create(self, sorter: TopologicalSorter) -> None:
        ...

    @abstractmethod
    def _flush_update(self, sorter: TopologicalSorter) -> None:
        ...

    @abstractmethod
    def _flush_delete(self, sorter: TopologicalSorter) -> None:
        ...

    @abstractmethod
    def _fetch(self) -> ModelT | None:
        ...

    def _flush_prep(self) -> None:
        """
        Propagate any values to fields if needed before flush.
        """
        ...

    @property
    @abstractmethod
    def _dependencies(self) -> set[Entity]:
        """
        Return entities this entity depends on.
        """
        ...


class EntityIdDescriptor:
    """
    Accessor for read-only entity id.

    :raises ReadOnlyError: Upon write attempt
    """

    def __get__(self, ent, objtype=None):
        return ent._entity_id

    def __set__(self, ent, val):
        raise ReadOnlyError("_entity_id", ent)
