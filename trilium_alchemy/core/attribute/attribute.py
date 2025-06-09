from __future__ import annotations

from abc import ABC, abstractmethod
from graphlib import TopologicalSorter
from typing import TYPE_CHECKING, Self

from trilium_client.exceptions import NotFoundException
from trilium_client.models.attribute import Attribute as EtapiAttributeModel

from ..entity.entity import BaseEntity, OrderedEntity, State
from ..entity.model import (
    BaseDriver,
    BaseEntityModel,
    FieldDescriptor,
    WriteOnceDescriptor,
)
from ..exceptions import _assert_validate
from ..session import Session, normalize_session

if TYPE_CHECKING:
    from ..note.note import Note
    from .label import Label
    from .relation import Relation

__all__ = [
    "BaseAttribute",
]


class AttributeDriver(BaseDriver):
    @property
    def attribute(self) -> BaseAttribute:
        return self.entity


class EtapiDriver(AttributeDriver):
    def fetch(self) -> EtapiAttributeModel | None:
        model: EtapiAttributeModel | None

        try:
            model = self.session.api.get_attribute_by_id(
                self.attribute.attribute_id
            )
        except NotFoundException:
            model = None

        return model

    def flush_create(self, sorter: TopologicalSorter):
        assert self.attribute._note is not None
        assert self.attribute._note.note_id is not None

        model = EtapiAttributeModel(
            note_id=self.attribute._note.note_id,
            type=self.attribute._attribute_type,
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
            self.attribute._attribute_type == "relation"
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


class AttributeModel(BaseEntityModel):
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
        "position": 10,
    }


class BaseAttribute(OrderedEntity[AttributeModel], ABC):
    """
    Encapsulates an attribute, a key-value record attached to a note.

    Can't be instantiated directly; use {obj}`Label` or {obj}`Relation`
    concrete classes.

    Once instantiated, the attribute needs to be added to a {obj}`Note`.
    See the documentation of {obj}`Note` for details.

    ```{note}
    Value is accessed differently depending on the concrete class:

    - {obj}`Label` has {obj}`Label.value`
    - {obj}`Relation` has {obj}`Relation.target`
    ```
    """

    _attribute_type: str
    _model_cls = AttributeModel
    _position: int = FieldDescriptor("position")

    # name of attribute, ensuring only one name is assigned
    _name: str = WriteOnceDescriptor("_name_obj")
    _name_obj: str | None = None

    # note which owns this attribute, ensuring only one note is assigned
    # - or None if not yet assigned to a note
    _note: Note | None = WriteOnceDescriptor("_note_obj")
    _note_obj: Note | None = None

    def __new__(cls, *_, **kwargs) -> Self:
        return super().__new__(
            cls,
            session=kwargs.get("session"),
            entity_id=kwargs.get("_attribute_id"),
            model_backing=kwargs.get("_model_backing"),
        )

    @abstractmethod
    def __init__(
        self,
        name: str,
        inheritable: bool = False,
        session: Session | None = None,
        _attribute_id: str | None = None,
        _owning_note: Note | None = None,
        _model_backing: AttributeModel | None = None,
    ):
        super().__init__(
            entity_id=_attribute_id,
            session=session,
            model_backing=_model_backing,
        )

        assert type(name) is str
        self._name = name

        # set owning note if we know it already (generally just for declarative
        # usage to generate deterministic id)
        if _owning_note is not None:
            self._note = _owning_note

        # set fields if not getting from database
        if _model_backing is None:
            self.inheritable = inheritable

    @property
    def attribute_id(self) -> str | None:
        """
        Getter for `attributeId`, or `None` if not created yet.
        """
        return self._entity_id

    @property
    def name(self) -> str:
        """
        Getter for attribute name.
        """
        return self._name

    @property
    def inheritable(self) -> bool:
        """
        Getter/setter for whether this attribute is inherited to
        children and by `template`/`inherit` relations.
        """
        return self._model.get_field("is_inheritable")

    @inheritable.setter
    def inheritable(self, val: bool):
        self._model.set_field("is_inheritable", val)

    @property
    def utc_date_modified(self) -> str:
        """
        UTC modified datetime, e.g. `2021-12-31 19:18:11.939Z`.
        """
        return self._model.get_field("utc_date_modified")

    @property
    def note(self) -> Note | None:
        """
        Getter for note which owns this attribute, or `None` if it hasn't
        been bound to a note yet.
        """
        return self._note

    @property
    def position(self) -> int:
        """
        Getter for position of this attribute.

        ```{note}
        This is maintained automatically based on the order of this attribute
        in its note's {obj}`Note.attributes` list.
        ```
        """
        return self._position

    @classmethod
    def _from_id(
        cls, attribute_id: str, session: Session | None = None
    ) -> Label | Relation:
        """
        Get instance of appropriate concrete class given an `attributeId`.
        """

        # need to know type in order to create appropriate subclass,
        # so get model from id first

        session = normalize_session(session)

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
        owning_note: Note = None,
    ) -> BaseAttribute:
        # localize import so as to not introduce circular dependency.
        # this is a rare case of an abstract class knowing about its
        # concrete classes
        from ..note.note import Note
        from .label import Label
        from .relation import Relation

        attr: BaseAttribute

        if model.type == "label":
            attr = Label(
                model.name,
                session=session,
                _attribute_id=model.attribute_id,
                _model_backing=model,
                _owning_note=owning_note,
            )

        elif model.type == "relation":
            attr = Relation(
                model.name,
                Note(note_id=model.value, session=session),
                session=session,
                _attribute_id=model.attribute_id,
                _model_backing=model,
                _owning_note=owning_note,
            )

        else:
            raise Exception(f"Unexpected attribute type: {model.type}")

        return attr

    def _setup(self, model: EtapiAttributeModel):
        assert model.note_id

        from ..note.note import Note

        if self._note_obj is None:
            self._note = Note(note_id=model.note_id, session=self._session)
        else:
            assert self._note_obj.note_id == model.note_id

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
    def _dependencies(self) -> set[BaseEntity]:
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

        # add dependency on child branches to avoid extra children getting
        # created
        # - children from templates will get created if the note does not
        # already have children
        for branch in self._note.branches.children:
            deps.add(branch)

        return deps
