from __future__ import annotations

from abc import ABC
from functools import wraps
from graphlib import TopologicalSorter
import logging

from trilium_client.models.attribute import Attribute as EtapiAttributeModel
from trilium_client.exceptions import NotFoundException

import trilium_alchemy
from ..exceptions import _assert_validate
from ..session import Session, require_session

from ..entity.entity import (
    Entity,
    EntityIdDescriptor,
    OrderedEntity,
    State,
)

from ..entity.model import (
    Driver,
    Model,
    FieldDescriptor,
    ReadOnlyFieldDescriptor,
    ReadOnlyDescriptor,
    WriteOnceDescriptor,
    require_model,
)

from .. import note

__all__ = [
    "Attribute",
]


class AttributeDriver(Driver):
    @property
    def attribute(self):
        return self.entity


class EtapiDriver(AttributeDriver):
    def fetch(self) -> EtapiAttributeModel | None:
        model: EtapiAttributeModel | None

        try:
            model = self.session.api.get_attribute_by_id(
                self.attribute.attribute_id
            )
        except NotFoundException as e:
            model = None

        return model

    def flush_create(self, sorter: TopologicalSorter):
        assert self.attribute._note is not None
        assert self.attribute._note.note_id is not None

        model = EtapiAttributeModel(
            note_id=self.attribute._note.note_id,
            type=self.attribute.attribute_type,
            name=self.attribute.name,
            **self.attribute._model._working,
        )

        if self.attribute.attribute_id is not None:
            model.attribute_id = self.attribute.attribute_id

        model_new = self.session.api.post_attribute(model)
        assert model_new is not None

        return model_new

    def flush_update(self, sorter: TopologicalSorter):
        # check if relation and target changed
        relation_update = (
            self.attribute.attribute_type == "relation"
            and self.attribute._model.is_field_changed("value")
        )

        # is_inheritable and target note (relation type only) are considered
        # immutable by Trilium; delete and create a new attribute if changed
        if relation_update or self.attribute._model.is_field_changed(
            "is_inheritable"
        ):
            self.flush_delete(sorter)
            return self.flush_create(sorter)
        else:
            # can just use patch
            model = EtapiAttributeModel(
                **self.attribute._model.get_fields_changed()
            )
            model_new = self.session.api.patch_attribute_by_id(
                self.attribute.attribute_id, model
            )
            assert model_new is not None

            return model_new

    def flush_delete(self, sorter: TopologicalSorter):
        self.session.api.delete_attribute_by_id(self.attribute.attribute_id)


class FileDriver(AttributeDriver):
    pass


class AttributeModel(Model):
    etapi_model = EtapiAttributeModel

    etapi_driver_cls = EtapiDriver

    file_driver_cls = FileDriver

    field_entity_id = "attribute_id"

    fields_update = [
        "value",
        "is_inheritable",
        "position",
    ]

    fields_default = {
        "value": "",
        "is_inheritable": False,
        "position": 0,
    }


def require_attribute_id(func):
    # ent: may be cls or self
    @wraps(func)
    def _require_attribute_id(ent, *args, **kwargs):
        if "attribute_id" not in kwargs:
            kwargs["attribute_id"] = None

        return func(ent, *args, **kwargs)

    return _require_attribute_id


class Attribute(OrderedEntity[AttributeModel], ABC):
    """
    Encapsulates an attribute, a key-value record attached to a note.

    Can't be instantiated directly; use {obj}`Label` or {obj}`Relation`
    concrete classes.

    Once instantiated, the attribute needs to be added to a {obj}`Note`.
    See the documentation of {obj}`Note.attributes` for details.

    ```{note}
    Value is accessed differently depending on the concrete class:

    - {obj}`Label` has {obj}`Label.value`
    - {obj}`Relation` has {obj}`Relation.target`
    ```
    """

    attribute_id: str = EntityIdDescriptor()
    """
    Read-only access to `attributeId`.
    """

    name: str = ReadOnlyDescriptor("_name")
    """
    Read-only access to attribute name.
    """

    inheritable: bool = FieldDescriptor("is_inheritable")
    """
    Whether this attribute is inherited to children and by
    `template`/`inherit` relations.
    """

    utc_date_modified: str = ReadOnlyFieldDescriptor("utc_date_modified")
    """
    UTC modified datetime, e.g. `2021-12-31 19:18:11.939Z`.
    """

    note: note.Note = ReadOnlyDescriptor("_note", allow_none=True)
    """
    Read-only access to note which owns this attribute.
    """

    position = ReadOnlyDescriptor("_position")
    """
    Read-only access to position of this attribute.

    ```{note}
    This is maintained automatically based on the order of this attribute
    in its note's {obj}`Note.attributes` list.
    ```
    """

    attribute_type: str = None
    """
    Type of attribute, to be populated by subclass.
    """

    _model_cls = AttributeModel

    _position = FieldDescriptor("position")

    # name of attribute, ensuring only one name is assigned
    _name = WriteOnceDescriptor("_name_")
    _name_: str = None

    # note which owns this attribute, ensuring only one note is assigned
    # may be None if not yet assigned to a note
    _note = WriteOnceDescriptor("_note_")
    _note_: note.Note | None = None

    @require_session
    @require_model
    @require_attribute_id
    def __new__(cls, *args, **kwargs):
        return super().__new__(
            cls,
            entity_id=kwargs["attribute_id"],
            session=kwargs["session"],
            model_backing=kwargs["model_backing"],
        )

    @require_session
    @require_model
    @require_attribute_id
    def __init__(self, name: str, inheritable: bool = False, **kwargs):
        attribute_id = kwargs.pop("attribute_id")
        session = kwargs.pop("session")
        model_backing = kwargs.pop("model_backing")
        owning_note = kwargs.pop("owning_note", None)

        if kwargs:
            logging.warning(f"Unexpected kwargs: {kwargs}")

        super().__init__(
            entity_id=attribute_id,
            session=session,
            model_backing=model_backing,
        )

        assert type(name) is str
        self._name = name

        # set owning note if we know it already (generally just for declarative
        # usage to generate deterministic id)
        if owning_note is not None:
            self._note = owning_note

        # set fields if not getting from database
        if model_backing is None:
            self.inheritable = inheritable

    @classmethod
    @require_session
    def _from_id(
        cls, attribute_id: str, session: Session = None
    ) -> trilium_alchemy.Label | trilium_alchemy.Relation:
        """
        Get instance of appropriate concrete class given an `attributeId`.
        """

        # need to know type in order to create appropriate subclass,
        # so get model from id first

        model: EtapiAttributeModel = session.api.get_attribute_by_id(
            attribute_id
        )
        assert model is not None

        return cls._from_model(model, session=session)

    @classmethod
    def _from_model(
        cls,
        model: EtapiAttributeModel,
        session: Session = None,
        owning_note: note.Note = None,
    ) -> Attribute:
        # localize import so as to not introduce circular dependency.
        # this is a rare case of an abstract class knowing about its
        # concrete classes
        from . import label, relation

        attr: Attribute

        if model.type == "label":
            attr = label.Label(
                model.name,
                attribute_id=model.attribute_id,
                model_backing=model,
                session=session,
                owning_note=owning_note,
            )

        elif model.type == "relation":
            attr = relation.Relation(
                model.name,
                note.Note(note_id=model.value, session=session),
                attribute_id=model.attribute_id,
                model_backing=model,
                session=session,
                owning_note=owning_note,
            )

        else:
            raise Exception(f"Unexpected attribute type: {model.type}")

        return attr

    def _setup(self, model: EtapiAttributeModel):
        assert model.note_id is not None and model.note_id != ""

        if self._note_ is None:
            self._note = note.Note(note_id=model.note_id, session=self._session)
        else:
            assert self._note_.note_id == model.note_id

    # override to handle deleting from note's list
    def _delete(self):
        super()._delete()

        if self._note is not None:
            if self in self._note.attributes.owned:
                self._note.attributes.owned.remove(self)

    def _flush_check(self):
        _assert_validate(
            self._note is not None, "Attribute not assigned to note"
        )

    @property
    def _dependencies(self) -> set[Entity]:
        """
        Attribute depends on note which owns it.
        """

        deps = {self._note}

        if self._state is not State.DELETE:
            # get index of this attribute
            index = self._note.attributes.owned.index(self)

            # add dependency on attributes before this one to enable
            # more deterministic flushing (e.g. to make failures
            # more reproducible)
            if index != 0:
                for i in range(index):
                    deps.add(self._note.attributes.owned[i])

        return deps
