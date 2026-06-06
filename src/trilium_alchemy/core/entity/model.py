from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from functools import wraps
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING, Any, Callable, Generator

from pydantic import BaseModel

from ..session import Session, SessionType
from .types import State

if TYPE_CHECKING:
    from .entity import BaseEntity

# TODO: parameterize BaseDriver and BaseEntityModel with BaseModel subclass
# for this entity


class BaseDriver(ABC):
    """
    Implements interface to backing store for note, either to Trilium itself
    (through ETAPI) or another mechanism like a filesystem.
    """

    entity: BaseEntity
    session: Session

    def __init__(self, entity: BaseEntity):
        self.entity = entity
        self.session = entity.session

    @abstractmethod
    def fetch(self) -> BaseModel | None:
        """
        Retrieve model from backing store, or None if it doesn't exist.
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


class BaseEntityModel(ABC):
    """
    Abstraction of data model which is stored as a record in Trilium's
    database, encapsulating both locally modified data and data as received
    from Trilium.
    """

    # pydantic model used in etapi
    etapi_model: type[BaseModel]

    # class to interface with ETAPI
    etapi_driver_cls: type[BaseDriver]

    # class to interface with filesystem
    file_driver_cls: type[BaseDriver]

    # fields allowed for user update
    fields_update: list[str]

    # default values of fields
    fields_default: dict[str, str]

    # entity owning this object
    entity: BaseEntity

    # cached data fetched from backing store, or None if not fetched
    _backing: dict[str, str | int | bool] | None = None

    # locally modified or created data not yet committed to backing store,
    # or None if not fetched
    _working: dict[str, str | int | bool] | None = None

    # whether model setup was completed, populating model from server
    _setup_done: bool = False

    # whether object exists in backing store, or None if unknown
    _exists: bool | None = None

    # list of stateful extensions registered by subclass
    _extensions: list[StatefulExtension]

    # driver to interface with backing store
    _driver: BaseDriver

    def __init__(self, entity: BaseEntity):
        self.entity = entity
        self._extensions = list()

        # select driver based on session type and instantiate
        driver_map = {
            SessionType.ETAPI: self.etapi_driver_cls,
            SessionType.FILE: self.file_driver_cls,
            # SessionType.VIRTUAL: None (set self._driver as None)
        }
        assert entity.session._type in driver_map

        self._driver = driver_map[entity.session._type](entity)

    def __str__(self):
        fields = list()

        def get_field_str(value: str | int | bool) -> str:
            return (
                f"'{value.replace(" '", "\\' ")}'"
                if isinstance(value, str)
                else str(value)
            )

        for field in self.fields_update:
            if self._backing is None:
                if self.entity._is_create:
                    backing = ""
                else:
                    backing = "?"
            else:
                backing = f"{get_field_str(self._backing[field])}"

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

                    working = f"{arrow}{get_field_str(self._working[field])}"

            fields.append(f"{field}={backing}{working}")

        fields_str = ", ".join(fields)

        return f"{{{fields_str}}}"

    @property
    def exists(self) -> bool:
        return bool(self._exists)

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

    def teardown(self):
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
                f: self._get_default_field(f) for f in self.fields_update
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

    # TODO: param check_type: check and return given type
    def get_field(self, field: str) -> str | int | bool | None:
        """
        Get field from model, with working state taking precedence over
        database state.
        """

        assert field in self._etapi_fields

        # perform model setup if not done
        self.setup_check()

        # attempt to get from working model
        if self._working is not None and field in self._working:
            # get field from working model
            return self._working[field]

        if not self.entity._is_create:
            # backing model should be populated at this point
            assert self._backing is not None

        # get field from backing model
        if self._backing is not None:
            return self._backing[field]

        # return None in case data is not available yet (e.g. accessing
        # date created when not created yet)
        return None

    def set_field(self, field: str, value: Any, bypass_validate: bool = False):
        """
        Set field in working model.
        """

        # ensure field is writeable
        assert field in self.fields_update

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

    def register_extension(self, extension: StatefulExtension):
        """
        Register extension to receive model updates and handle teardown().
        Only stateful extensions are registered.
        """
        self._extensions.append(extension)

    def flush_extensions(self) -> BaseModel | None:
        """
        Flush extensions and return the latest model, if applicable.
        """
        model_new: BaseModel | None = None

        for ext in self._extensions:
            if ext._is_changed:
                model_new = ext._flush() or model_new

        return model_new

    def _get_default_field(self, field: str) -> str:
        """
        Get default field for initializing working model.
        """
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
    _model: BaseEntityModel = None

    def __init__(self, model: BaseEntityModel):
        self._model = model


class Extension(ABC, ModelContainer):
    """
    Enables an entity to be extended with additional state besides the
    entity's model.
    """

    _entity: BaseEntity

    def __init__(self, entity: BaseEntity):
        ModelContainer.__init__(self, entity._model)
        self._entity = entity

    @abstractmethod
    def _setattr(self, val: Any):
        """
        Invoked to set data.
        """
        ...


class StatefulExtension(Extension):
    """
    Extension which has state derived by model. This state is populated during
    setup() and cleared during teardown().
    """

    # TODO: driver to handle fetch, flush

    def __init__(self, entity: BaseEntity):
        super().__init__(entity)
        entity._model.register_extension(self)

    @abstractmethod
    def _setup(self, model: BaseModel | None):
        """
        Invoked after model is initially setup, or if a model is refreshed.
        """
        ...

    @abstractmethod
    def _teardown(self):
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

    def _flush(self) -> BaseModel | None:
        """
        Commit changes to database, returning the latest model if applicable.
        """
        ...


def require_setup(func):
    @wraps(func)
    def wrapper(self, ent: BaseEntity, objtype=None):
        ent._model.setup_check()
        return func(self, ent, objtype)

    return wrapper


def require_setup_prop(func):
    if isinstance(func, property):
        # if decorating a property, wrap its getter and return a new property
        getter = require_setup_prop(func.fget)
        setter = (
            require_setup_prop(func.fset) if func.fset is not None else None
        )
        return property(getter, setter, func.fdel, func.__doc__)

    @wraps(func)
    def wrapper(self: BaseEntity, *args, **kwargs):
        self._model.setup_check()
        return func(self, *args, **kwargs)

    return wrapper


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

    def __get__(self, ent: BaseEntity, objtype=None):
        return ent._model.get_field(self._field)

    def __set__(self, ent: BaseEntity, val: Any):
        ent._model.set_field(self._field, val)


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
    def __get__(self, ent: BaseEntity, objtype=None) -> Any:
        return getattr(ent, self._attr)

    def __set__(self, ent: BaseEntity, value: Any):
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
    def __get__(self, ent: BaseEntity, objtype=None) -> Any:
        return getattr(ent, self._attr)

    def __set__(self, ent: BaseEntity, value: Any):
        assert value is not None

        value_current = getattr(ent, self._attr)

        if value_current is None:
            setattr(ent, self._attr, value)
        else:
            # make sure value isn't being changed, would be internal error
            assert value_current == value

        # invoke validator
        if self._validator:
            getattr(ent, self._validator)()
