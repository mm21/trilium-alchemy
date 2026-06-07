from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from functools import wraps
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING, Any, Generator, Literal, Self, overload

from pydantic import BaseModel

from ..session import Session
from .types import State

if TYPE_CHECKING:
    from .entity import BaseEntity


class BaseDriver[ModelT: BaseModel](ABC):
    """
    Implements interface to backing store for note, either to Trilium itself (through
    ETAPI) or another mechanism like a filesystem.
    """

    entity: BaseEntity
    session: Session

    def __init__(self, entity: BaseEntity):
        self.entity = entity
        self.session = entity.session

    @abstractmethod
    def fetch(self) -> ModelT | None:
        """
        Retrieve model from backing store, or None if it doesn't exist.
        """
        ...

    @abstractmethod
    def flush_create(self, sorter: TopologicalSorter) -> ModelT:
        """
        Create entity.
        """
        ...

    @abstractmethod
    def flush_update(self, sorter: TopologicalSorter) -> ModelT:
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


# TODO: parameterize BaseEntityModel with BaseModel subclass, BaseDriver subclass
# for this entity


class BaseEntityModel(ABC):
    """
    Abstraction of data model which is stored as a record in Trilium's database,
    encapsulating both locally modified data and data as received from Trilium.
    """

    # entity owning this object
    entity: BaseEntity

    # driver to interface with backing store
    driver: BaseDriver

    # cached data fetched from backing store, or None if not fetched
    backing_data: dict[str, Any] | None = None

    # locally modified or created data not yet committed to backing store,
    # or None if not fetched
    working_data: dict[str, Any] | None = None

    # whether model setup was completed, populating model from server
    _setup_done: bool = False

    # whether object exists in backing store, or None if unknown
    _exists: bool | None = None

    # list of stateful extensions registered by subclass
    _extensions: list[StatefulExtension]

    def __init__(self, entity: BaseEntity):
        self.entity = entity
        self.driver = self.driver_cls(entity)
        self._extensions = []

    def __str__(self):
        fields = []

        def get_field_str(value: str | int | bool) -> str:
            return (
                f"'{value.replace(" '", "\\' ")}'"
                if isinstance(value, str)
                else str(value)
            )

        for field in self.update_fields:
            if self.backing_data is None:
                if self.entity._is_create:
                    backing = ""
                else:
                    backing = "?"
            else:
                backing = f"{get_field_str(self.backing_data[field])}"

            if self.working_data is None or not self.is_changed:
                working = ""
            else:
                if (
                    self.backing_data is not None
                    and self.backing_data[field] == self.working_data[field]
                ):
                    working = ""
                else:
                    if self.entity._is_create:
                        arrow = ""
                    else:
                        arrow = "->"

                    working = f"{arrow}{get_field_str(self.working_data[field])}"

            fields.append(f"{field}={backing}{working}")

        fields_str = ", ".join(fields)

        return f"{{{fields_str}}}"

    @property
    def exists(self) -> bool:
        """
        Whether the model for certain exists.
        """
        return bool(self._exists)

    @property
    def nexists(self) -> bool:
        """
        Whether the model for certain does not exist (setup is additionally done).
        """
        return self._exists is False and self._setup_done

    @property
    @abstractmethod
    def etapi_model(self) -> type[BaseModel]:
        """
        Pydantic model used in etapi.
        """
        ...

    @property
    @abstractmethod
    def driver_cls(self) -> type[BaseDriver]:
        """
        Class to interface with ETAPI.
        """
        ...

    @property
    @abstractmethod
    def entity_id_field(self) -> str:
        """
        Field used to store entity id.
        """
        ...

    @property
    @abstractmethod
    def update_fields(self) -> list[str]:
        """
        Fields allowed for user update.
        """
        ...

    @property
    @abstractmethod
    def default_fields(self) -> dict[str, Any]:
        """
        Default values of fields.
        """
        ...

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
            State.CREATE: self.driver.flush_create,
            State.UPDATE: self.driver.flush_update,
            State.DELETE: self.driver.flush_delete,
        }[self.entity._state]

        # invoke flush method
        new_model: BaseModel | None
        if inspect.isgeneratorfunction(func):
            # generator function: yields model, then performs extra processing
            gen = func(sorter)
            new_model = next(gen)
        else:
            # not generator function: just returns model
            gen = None
            new_model = func(sorter)

        # ensure we got the updated model
        if self.entity._state in [State.CREATE, State.UPDATE]:
            assert new_model is not None
        else:
            assert new_model is None

        if self.entity._state is State.CREATE:
            # set entity id if needed
            if self.entity._entity_id is None:
                entity_id = getattr(new_model, self.entity_id_field)
                self.entity._set_entity_id(entity_id)

        return (new_model, gen)

    @property
    def fields_changed(self) -> bool:
        if self.working_data is None or self.backing_data is None:
            return False
        else:
            backing = {k: self.backing_data[k] for k in self.update_fields}
            return backing != self.working_data

    @property
    def extension_changed(self) -> bool:
        return any(ext._is_changed for ext in self._extensions)

    @property
    def is_changed(self) -> bool:
        return self.entity._is_create or self.fields_changed or self.extension_changed

    def is_field_changed(self, field) -> bool:
        if self.working_data is None or self.backing_data is None:
            return False

        return self.backing_data[field] != self.working_data[field]

    def get_fields_changed(self) -> dict[str, Any]:
        """
        Return a dict of all fields which are changed.
        """
        fields = dict()

        for field in self.update_fields:
            if self.backing_data[field] != self.working_data[field]:
                fields[field] = self.working_data[field]

        return fields

    def teardown(self):
        self.backing_data = None
        self.working_data = None
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
        Setup model if necessary and backing model provided during init (entity already
        retrieved from database).
        """
        setup = False

        if create:
            setup = True
        elif model is not None and self.check_newer(model):
            # no existing model or provided model is newer
            setup = True

        if setup:
            self.setup(model=model, create=create)

    def check_newer(self, model: BaseModel) -> bool:
        return (
            self.backing_data is None
            or model.utc_date_modified > self.backing_data["utc_date_modified"]
        )

    def setup(self, model: BaseModel | None = None, create: bool | None = None):
        """
        Populate state from database for this object.

        May occur any number of times per object.
        """
        if create is True:
            # if creating, just set flag: no need to query database
            self._exists = False

            # there can't be a backing model if it doesn't exist in db
            assert model is None
        else:
            # attempt to fetch from database if not provided
            if model is None:
                model = self.driver.fetch()

            if model is None:
                self.backing_data = None

                # create is False means expected to exist
                assert create is None
            else:
                self.backing_data = dict(model)

            # set exists flag
            self._exists = self.backing_data is not None

        # populate working fields
        if self._exists:
            # reset fields if any; will create on demand if needed
            self.working_data = None
        else:
            # populate new working fields
            self.working_data = {
                f: self._get_default_field(f) for f in self.update_fields
            }

            # move to create state
            self.entity._set_dirty(State.CREATE)

        if model is not None:
            # invoke setup callback for entity
            self.entity._setup(model)

        # set setup_done before extensions are setup; they may refer to state
        # from model (e.g. is_string requires note's type and mime fields)
        self._setup_done = True

        if self._extensions is not None:
            # invoke setup callback for extensions
            for ext in self._extensions:
                ext._setup(model)

    @overload
    def get_field[T](
        self, field: str, check_type: type[T], *, allow_none: Literal[False] = False
    ) -> T: ...

    @overload
    def get_field[T](
        self, field: str, check_type: type[T], *, allow_none: Literal[True]
    ) -> T | None: ...

    def get_field[T](
        self, field: str, check_type: type[T], *, allow_none: bool = False
    ) -> T | None:
        """
        Get field from model, with working state taking precedence over database state.
        """
        assert field in self.etapi_model.model_fields

        def get_value(data: dict[str, Any]) -> T | None:
            assert field in data
            val = data[field]
            if val is not None or not allow_none:
                assert isinstance(val, check_type)
            return val

        # perform model setup if not done
        self.setup_check()

        # attempt to get value from working model
        if self.working_data and field in self.working_data:
            return get_value(self.working_data)

        if not self.entity._is_create:
            # backing model should be populated at this point
            assert self.backing_data

        # attempt to get value from backing model
        if self.backing_data:
            return get_value(self.backing_data)

        # return None in case data is not available yet (e.g. accessing
        # date created when not created yet)
        assert allow_none
        return None

    def set_field(self, field: str, value: Any, *, bypass_validate: bool = False):
        """
        Set field in working model.
        """
        # ensure field is writeable
        assert field in self.update_fields

        # perform model setup if not done
        self.setup_check()

        # check if working model is initialized
        if self.working_data is None:
            # backing model should exist: working model populated for create
            assert self.backing_data is not None

            # populate working model with copy of backing model, filtered by
            # fields used for update
            self.working_data = {k: self.backing_data[k] for k in self.update_fields}

        if not bypass_validate:
            # validate fields for setting
            assert field in self.update_fields

        # handle deleted state
        if self.entity._state is State.DELETE:
            raise Exception(
                f"Attempt to set field={field} on entity={self} marked for delete"
            )

        # set field in working model
        self.working_data[field] = value

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
        new_model: BaseModel | None = None

        for ext in self._extensions:
            if ext._is_changed:
                new_model = ext._flush() or new_model

        return new_model

    def _get_default_field(self, field: str) -> str:
        """
        Get default field for initializing working model.
        """
        assert field in self.default_fields
        return self.default_fields[field]


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
    Enables an entity to be extended with additional state besides the entity's model.
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
    Extension which has state derived by model.

    This state is populated during setup() and cleared during teardown().
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

        Stateful extensions may or may not have state needing to be flushed. Default to
        not requiring flush (currently only note content requires flush).
        """
        return False

    def _flush(self) -> BaseModel | None:
        """
        Commit changes to database, returning the latest model if applicable.
        """
        ...


def require_setup_prop(func):
    if isinstance(func, property):
        # if decorating a property, wrap its getter and return a new property
        getter = require_setup_prop(func.fget)
        setter = require_setup_prop(func.fset) if func.fset is not None else None
        return property(getter, setter, func.fdel, func.__doc__)

    @wraps(func)
    def wrapper(self: BaseEntity, *args, **kwargs):
        self._model.setup_check()
        return func(self, *args, **kwargs)

    return wrapper


class WriteThroughDescriptor[T]:
    """
    Accessor for class attribute which immediately populates the underlying model field
    when updated.
    """

    # attribute which holds value for reading
    _attr: str

    # attribute of object which holds value for writing
    _obj_attr: str

    # name of model field to be set
    _field: str

    def __init__(self, attr: str, obj_attr: str, field: str):
        self._attr = attr
        self._obj_attr = obj_attr
        self._field = field

    @overload
    def __get__(self, obj: None, objtype: type) -> Self: ...
    @overload
    def __get__(self, obj: BaseEntity, objtype: type) -> T: ...
    def __get__(self, obj: BaseEntity | None, objtype: type) -> Self | T:
        _ = objtype
        if obj is None:
            return self
        obj._model.setup_check()
        return getattr(obj, self._attr)

    def __set__(self, obj: BaseEntity, value: T):
        assert value is not None
        setattr(obj, self._attr, value)
        obj._model.set_field(self._field, getattr(value, self._obj_attr))


class WriteOnceDescriptor[T]:
    """
    Accessor for field which is only allowed a single value.

    Subsequent assignments are a no-op if they set the same value.

    :raises ReadOnlyError: Upon write attempt with different value than currently set
    """

    # attribute which holds value
    _attr: str

    # name of method to invoke after setting value
    _validator: str | None

    def __init__(self, attr, *, validator: str | None = None):
        self._attr = attr
        self._validator = validator

    @overload
    def __get__(self, obj: None, objtype: type) -> Self: ...
    @overload
    def __get__(self, obj: BaseEntity, objtype: type) -> T: ...
    def __get__(self, obj: BaseEntity | None, objtype: type) -> Self | T:
        _ = objtype
        if obj is None:
            return self
        obj._model.setup_check()
        return getattr(obj, self._attr)

    def __set__(self, obj: BaseEntity, value: T):
        if value is None:
            raise ValueError(f"Cannot set {self._attr} with value None on {obj}")

        cur_value = getattr(obj, self._attr)

        if cur_value is None:
            setattr(obj, self._attr, value)
        elif value != cur_value:
            raise ValueError(f"New value {value} must equal current value {cur_value}")

        if validator := self._validator:
            getattr(obj, validator)()
