from __future__ import annotations

from typing import Any, Callable, Generator, Iterable
from abc import ABC, abstractmethod
from functools import wraps
from graphlib import TopologicalSorter
import inspect
import logging

from pydantic import BaseModel

from ..exceptions import *
from ..session import Session, SessionType

from . import entity as entity_abc
from .types import State


def require_model(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "model_backing" not in kwargs:
            kwargs["model_backing"] = None

        return func(*args, **kwargs)

    return wrapper


class Driver(ABC):
    """
    Implements interface to backing note storage, either to Trilium itself
    (through ETAPI) or a filesystem.
    """

    entity: entity_abc.Entity = None

    session: Session = None

    def __init__(self, entity):
        self.entity = entity
        self.session = entity.session

    @abstractmethod
    def fetch(self) -> BaseModel | None:
        """
        Retrieve model from backing storage, or None if it doesn't exist.
        """
        ...

    @abstractmethod
    def flush_create(self, sorter: TopologicalSorter):
        """
        Create entity.
        """
        ...

    @abstractmethod
    def flush_update(self, sorter: TopologicalSorter):
        """
        Update entity.
        """
        ...

    @abstractmethod
    def flush_delete(self, sorter: TopologicalSorter):
        """
        Delete entity.
        """
        ...


class Model(ABC):
    """
    Abstraction of data model which is stored as a record in Trilium's
    database, encapsulating both locally modified data and data as received
    from Trilium.
    """

    # pydantic model used in etapi
    etapi_model: type[BaseModel] = None

    # class to interface with ETAPI
    etapi_driver_cls: type[Driver] = None

    # class to interface with filesystem
    file_driver_cls: type[Driver] = None

    # mapping of alias to field name
    fields_alias: dict[str, str] = None

    # fields allowed for user update
    fields_update: list[str] = None

    # default values of fields
    fields_default: dict[str, str] = None

    # entity owning this object
    entity: entity_abc.Entity = None

    # cached data fetched from backing storage
    _backing: dict[str, str | int | bool] = None

    # locally modified or created data, not committed to backing storage
    _working: dict[str, str | int | bool] = None

    # whether model setup was completed (populating data from server)
    _setup_done: bool = False

    # whether object exists in backing storage (None if unknown)
    _exists: bool | None = None

    # list of stateful extensions registered by subclass
    _extensions: list[StatefulExtension] = None

    # driver to interface with backing storage, or None
    # if in-memory only (for VirtualSession)
    _driver: Driver | None = None

    def __init__(self, entity: entity_abc.Entity):
        self.entity = entity
        self._extensions = list()

        # select driver based on session type and instantiate
        driver_map = {
            SessionType.ETAPI: self.etapi_driver_cls,
            SessionType.FILE: self.file_driver_cls,
        }

        if entity.session._type in driver_map:
            self._driver = driver_map[entity.session._type](entity)

    def __str__(self):
        fields = list()

        for field in self.fields_update:
            if self._backing is None:
                if self.entity._is_create:
                    backing = ""
                else:
                    backing = "?"
            else:
                backing = self._backing[field]

            if self._working is None or not self.is_changed:
                working = ""
            else:
                if (
                    self._backing is not None
                    and self._backing[field] == self._working[field]
                ):
                    working = ""
                else:
                    if self.entity._is_create:
                        arrow = ""
                    else:
                        arrow = "->"

                    working = f"{arrow}{self._working[field]}"

            fields.append(f"{field}={backing}{working}")

        fields_str = ", ".join(fields)

        return f"{{{fields_str}}}"

    @classmethod
    @property
    def fields_update_alias(cls) -> Iterable[str]:
        """
        Maps aliased fields to canonical fields using fields_alias if
        provided.
        """
        if cls.fields_alias:
            fields_update = cls.fields_update.copy()
            for alias, field in cls.fields_alias.items():
                if field in fields_update:
                    fields_update[fields_update.index(field)] = alias

            return fields_update
        else:
            return cls.fields_update

    @property
    def exists(self) -> bool:
        return self._exists

    @property
    def _nexists(self) -> bool:
        return self._exists is False and self._setup_done

    def flush(
        self, sorter: TopologicalSorter
    ) -> tuple[BaseModel | None, Generator | None]:
        """
        Flush model if any fields are changed.
        """

        if self.entity._state in [State.CREATE, State.UPDATE]:
            # if creating or updating, invoke flush prep
            self.entity._flush_prep()

        assert self._driver is not None

        # get flush method based on state
        func = {
            State.CREATE: self._driver.flush_create,
            State.UPDATE: self._driver.flush_update,
            State.DELETE: self._driver.flush_delete,
        }[self.entity._state]

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
        if self.entity._state in [State.CREATE, State.UPDATE]:
            assert model_new is not None
        else:
            assert model_new is None

        if self.entity._state is State.CREATE:
            # set entity id if needed
            if self.entity._entity_id is None:
                entity_id = getattr(model_new, self.field_entity_id)
                self.entity._set_entity_id(entity_id)

        return (model_new, gen)

    @property
    def fields_changed(self) -> bool:
        if self._working is None or self._backing is None:
            return False
        else:
            backing = {k: self._backing[k] for k in self.fields_update}
            return backing != self._working

    @property
    def extension_changed(self) -> bool:
        return any(ext._is_changed for ext in self._extensions)

    @property
    def is_changed(self) -> bool:
        return (
            self.entity._is_create
            or self.fields_changed
            or self.extension_changed
        )

    def is_field_changed(self, field) -> bool:
        if self._working is None or self._backing is None:
            return False

        return self._backing[field] != self._working[field]

    def get_fields_changed(self) -> dict[str, Any]:
        """
        Return a dict of all fields which are changed.
        """
        fields = dict()

        for field in self.fields_update:
            if self._backing[field] != self._working[field]:
                fields[field] = self._working[field]

        return fields

    @property
    def setup_done(self) -> bool:
        return self._setup_done

    def teardown(self) -> None:
        self._backing = None
        self._working = None
        self._setup_done = False

        for ext in self._extensions:
            ext._teardown()

    def setup_check(self):
        """
        Setup model if not already done, prior to get/set access.
        """
        if self._setup_done is False:
            self.setup()

    def setup_check_init(self, model: BaseModel, create: bool | None = None):
        """
        Setup model if necessary and backing model provided
        during init (entity already retrieved from database).
        """
        setup = False

        if create:
            setup = True
        elif model is not None and self.check_newer(model):
            # no existing model or provided model is newer
            setup = True

        if setup:
            self.setup(model_backing=model, create=create)

    def check_newer(self, model: BaseModel) -> bool:
        return (
            self._backing is None
            or model.utc_date_modified > self._backing["utc_date_modified"]
        )

    def setup(
        self, model_backing: BaseModel | None = None, create: bool | None = None
    ):
        """
        Populate state from database for this object. May occur any number of times
        per object.
        """

        if create is True:
            # if creating, just set flag: no need to query database
            self._exists = False

            # there can't be a backing model if it doesn't exist in db
            assert model_backing is None
        else:
            # attempt to fetch from database if not provided
            if model_backing is None:
                model_backing = self._driver.fetch()

            if model_backing is None:
                self._backing = None

                # create is False means expected to exist
                assert create is None
            else:
                self._backing = dict(model_backing)

            # set exists flag
            self._exists = self._backing is not None

        # populate working fields
        if self._exists:
            # reset fields if any; will create on demand if needed
            self._working = None
        else:
            # populate new working fields
            self._working = {
                f: self._field_default(f) for f in self.fields_update
            }

            # move to create state
            self.entity._set_dirty(State.CREATE)

        if model_backing is not None:
            # invoke setup callback for entity
            self.entity._setup(model_backing)

        # set setup_done before extensions are setup; they may refer to state
        # from model (e.g. is_string requires note's type and mime fields)
        self._setup_done = True

        if self._extensions is not None:
            # invoke setup callback for extensions
            for ext in self._extensions:
                ext._setup(model_backing)

    def get_field(self, field, bypass_model_setup=False):
        """
        Get field from model, with working state taking precedence over
        database state.
        """

        assert field in self._etapi_fields

        # perform model setup if not done
        if not bypass_model_setup:
            self.setup_check()

        # attempt to get from working model
        if self._working is not None and field in self._working:
            # get field from working model
            return self._working[field]

        if bypass_model_setup:
            if self._backing is None:
                return None
        else:
            if not self.entity._is_create:
                # backing model should be populated at this point
                # if model setup was not bypassed
                assert self._backing is not None

        # get field from backing model
        if self._backing is not None:
            return self._backing[field]

        # return None in case data is not available yet (e.g. accessing
        # date created when not created yet)

    def set_field(self, field, value, bypass_validate=False):
        """
        Set field in working model.
        """

        # ensure field is writeable
        if field not in self.fields_update:
            raise ReadOnlyError(field, self.entity)

        # perform model setup if not done
        self.setup_check()

        # check if working model is initialized
        if self._working is None:
            # backing model should exist: working model populated for create
            assert self._backing is not None

            # populate working model with copy of backing model, filtered by
            # fields used for update
            self._working = {k: self._backing[k] for k in self.fields_update}

        if not bypass_validate:
            # validate fields for setting
            assert field in self.fields_update

        # handle deleted state
        if self.entity._state is State.DELETE:
            raise Exception(
                f"Attempt to set field={field} on entity={self} marked for delete"
            )

        # set field in working model
        self._working[field] = value

        # set as dirty/clean if needed
        self.entity._check_state()

    def register_extension(self, extension: StatefulExtension) -> None:
        """
        Register extension to receive model updates and handle teardown().
        Only stateful extensions are registered.
        """
        self._extensions.append(extension)

    def flush_extensions(self):
        for ext in self._extensions:
            if ext._is_changed:
                ext._flush()

    def _field_default(self, field: str) -> str:
        """
        Get default field for initializing working model.
        """

        # translate field alias if needed
        if self.fields_alias and field in self.fields_alias:
            field = self.fields_alias[field]

        assert field in self.fields_default, f"{field} not in defaults"
        return self.fields_default[field]

    @property
    def _etapi_fields(self) -> set[str]:
        """
        Return all fields in pydantic model.
        """
        return {k for k in self.etapi_model.model_fields.keys()}


class ModelContainer:
    """
    Indicates that subclasses contain a model instance.
    """

    # instance of Model
    _model: Model = None

    def __init__(self, model: Model):
        self._model = model


class Extension(ABC, ModelContainer):
    """
    Enables an entity to be extended: ensures model is setup when accessed
    and routes setattr() via ExtensionDescriptor.
    """

    _entity: entity_abc.Entity = None

    def __init__(self, entity: entity_abc.Entity):
        ModelContainer.__init__(self, entity._model)
        self._entity = entity

    @abstractmethod
    def _setattr(self, val: Any) -> None:
        """
        Invoked when an attribute mapped by ExtensionDescriptor is set by the
        user.
        """
        ...


class StatefulExtension(Extension):
    """
    Extension which has state derived by model. This state is populated during
    setup() and cleared during teardown().
    """

    # TODO: driver to handle fetch, flush

    def __init__(self, entity: entity_abc.Entity):
        super().__init__(entity)
        entity._model.register_extension(self)

    @abstractmethod
    def _setup(self, model: BaseModel | None) -> None:
        """
        Invoked after model is initially setup, or if a model is refreshed.
        """
        ...

    @abstractmethod
    def _teardown(self) -> None:
        """
        Reset current state.
        """
        ...

    @property
    def _is_changed(self) -> bool:
        """
        Returns whether there is a state needing to be flushed.

        Stateful extensions may or may not have state needing to be flushed.
        Default to not requiring flush (currently only note content requires
        flush).
        """
        return False

    def _flush(self):
        """
        Commits changes to database.
        """
        ...


def require_setup(func):
    @wraps(func)
    def _require_setup(self, ent: entity_abc.Entity, objtype=None):
        ent._model.setup_check()
        return func(self, ent, objtype)

    return _require_setup


class FieldDescriptor:
    """
    Accessor for a model field, e.g. a {obj}`Note`'s `title` field.

    When written, updates the working state which will be committed
    to Trilium upon flush. When read, returns the working state if
    set by user, or the state from Trilium if not.
    """

    _field: str

    def __init__(self, field: str):
        self._field = field

    def __get__(self, ent, objtype=None):
        return ent._model.get_field(self._field)

    def __set__(self, ent, val):
        ent._model.set_field(self._field, val)


# FieldDescriptor internally raises ReadOnlyError; use this to easily document
# that it's read-only
class ReadOnlyFieldDescriptor(FieldDescriptor):
    """
    Accessor for a read-only model field, e.g. a {obj}`Note`'s
    `date_created` field.

    :raises ReadOnlyError: Upon write attempt
    """


class ReadOnlyDescriptor:
    """
    Accessor for read-only class attribute.

    :raises ReadOnlyError: Upon write attempt
    """

    _attr: str

    # name of callback used to check if None is allowed
    _allow_none_cb: str

    _allow_none: bool

    def __init__(
        self,
        attr: str,
        allow_none_cb: str | None = None,
        allow_none: bool = False,
    ):
        self._attr = attr
        self._allow_none_cb = allow_none_cb
        self._allow_none = allow_none

    @require_setup
    def __get__(self, ent: entity_abc.Entity, objtype=None):
        # access value
        val = getattr(ent, self._attr)

        if val is None and not self._allow_none:
            # check if allowed to be None
            if self._allow_none_cb is None:
                allow_none = False
            else:
                allow_none_cb = getattr(ent, self._allow_none_cb)
                allow_none = allow_none_cb(ent)

            assert allow_none is True, f"Field {self._attr} is None"

        return val

    def __set__(self, ent: entity_abc.Entity, val):
        raise ReadOnlyError(self._attr, ent)


class WriteThroughDescriptor:
    """
    Accessor for class attribute which immediately populates the
    underlying model field when updated.
    """

    # attribute which holds value
    _attr: str

    # attribute of attribute containing value set in model
    _attr_attr: str

    # name of model field to be set
    _field: str

    def __init__(self, attr: str, attr_attr: str, field: str):
        self._attr = attr
        self._attr_attr = attr_attr
        self._field = field

    @require_setup
    def __get__(self, ent: entity_abc.Entity, objtype=None) -> Any:
        return getattr(ent, self._attr)

    def __set__(self, ent: entity_abc.Entity, value: Any):
        assert value is not None

        # set attr of entity
        setattr(ent, self._attr, value)

        # write through to model
        ent._model.set_field(self._field, getattr(value, self._attr_attr))


class WriteOnceDescriptor:
    """
    Accessor for field which is only allowed a single value. Subsequent
    assignments are a no-op if they set the same value.

    :raises ReadOnlyError: Upon write attempt with different value than
    currently set
    """

    # attribute which holds value
    _attr: str

    # callback to invoke after setting value
    _validator: Callable

    def __init__(self, attr: str, validator: Callable = None):
        self._attr = attr
        self._validator = validator

    @require_setup
    def __get__(self, ent: entity_abc.Entity, objtype=None) -> Any:
        return getattr(ent, self._attr)

    def __set__(self, ent: entity_abc.Entity, value: Any):
        assert value is not None

        value_current = getattr(ent, self._attr)

        if value_current is None:
            setattr(ent, self._attr, value)
        else:
            # make sure value isn't being changed
            if value_current != value:
                raise ReadOnlyError(self._attr, ent)

        # invoke validator
        if self._validator:
            getattr(ent, self._validator)()


class ExtensionDescriptor:
    """
    Accessor for model extension.

    A model extension performs additional processing on the model and provides
    an interface to update other entities associated with this entity.
    For example, {obj}`Note` uses an extension to process the list of
    attributes from the note model and create {obj}`Attribute` instances.
    """

    _attr: str

    def __init__(self, attr: str):
        self._attr = attr

    @require_setup
    def __get__(self, container: ModelContainer, objtype=None):
        return getattr(container, self._attr)

    @require_setup
    def __set__(self, container: ModelContainer, val):
        getattr(container, self._attr, val)._setattr(val)
