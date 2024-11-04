from __future__ import annotations

from collections import OrderedDict
from collections.abc import MutableSequence, Sequence
from typing import Any, Iterator, Type, TypeVar

from trilium_client.models.note import Note as EtapiNoteModel

from ..attribute import attribute, label, relation
from ..attribute.attribute import BaseAttribute
from ..entity.model import require_setup_prop
from ..exceptions import *
from . import note
from .extension import BaseEntityList, NoteExtension, NoteStatefulExtension

__all__ = [
    "Attributes",
    "OwnedAttributes",
    "InheritedAttributes",
]

# value specification:
# - str: label value
# - Note: relation target
# - tuple: label value/relation target with attribute kwargs
ValueSpec = TypeVar(
    "ValueSpec",
    str,
    Type["note.Note"],
    tuple[str | Type["note.Note"], dict[str, Any]],
)


class NameMap:
    """
    Provides lookup by name and implements dict-like "get" access
    by name or index.
    "Set" is implemented by specific class depending on its
    relevance.
    """

    # TODO: could return a dict of generators instead of dict of lists
    # (sometimes we only care about the first result)
    @property
    def _name_map(self) -> dict[str, list[attribute.BaseAttribute]]:
        attrs = dict()
        for attr in list(self):
            if attr.name in attrs:
                attrs[attr.name].append(attr)
            else:
                attrs[attr.name] = [attr]
        return attrs

    def __getitem__(self, key: str | int) -> list[attribute.BaseAttribute]:
        """
        If key is an int:
            Get attribute by index
        If key is a str:
            Get list of attributes with provided name
        """
        if type(key) is str:
            attrs = []

            for attr in list(self):
                if attr.name == key:
                    attrs.append(attr)

            if len(attrs):
                return attrs
            else:
                raise KeyError
        else:
            return list(self)[key]

    def __contains__(self, key: str | attribute.BaseAttribute) -> bool:
        """
        This can be invoked by name or by object.
        """

        # check name first, then defer to super to check object
        if key in self._name_map:
            return True
        return super().__contains__(key)


# TODO: deprecate name access, reuse BaseFilteredAttributes
class OwnedAttributes(NameMap, BaseEntityList[attribute.BaseAttribute]):
    """
    Interface to a note's owned attributes.
    """

    _child_cls = attribute.BaseAttribute
    _owner_field = "_note"

    def __str__(self):
        if self._entity_list is not None and len(self._entity_list) > 0:
            s = "\n".join([str(e) for e in self._entity_list])
        else:
            s = "No attributes"
        return f"{s}"

    def __setitem__(self, key: str | int, value_spec: ValueSpec):
        """
        Create attribute with provided name and optional kwargs.
        """

        if type(key) is str:
            name = key

            # assigning to note.attributes['name'] or
            # note.attributes.owned['name']:
            # - create attribute if no attribute with provided name exists
            # - update value of first attribute with provided name

            name_map = self._name_map

            if name not in name_map:
                self.append(self._create_attribute(name, value_spec))
            else:
                attr = name_map[name][0]

                value, kwargs = normalize_value_spec(value_spec)

                # update value based on type
                if isinstance(value, note.Note):
                    assert isinstance(attr, relation.Relation)
                    attr.target = value
                else:
                    assert type(value) is str
                    assert isinstance(attr, label.Label)
                    attr.value = value

                # update kwargs
                for key in kwargs:
                    setattr(attr, key, kwargs[key])
        else:
            # attributes.owned[index]: invoke superclass
            super().__setitem__(key, value_spec)

    def __delitem__(self, key: str | int):
        """
        Delete all owned attributes with provided name.
        """

        if type(key) is str:
            for attr in list(self):
                if attr.name == key:
                    attr.delete()
        else:
            super().__delitem__(key)

    def __iter__(self) -> Iterator[BaseAttribute]:
        return iter(self._entity_list)

    def _setup(self, model: EtapiNoteModel | None):
        # only populate if None (no changes by user or explicitly called
        # invalidate()) - don't want to discard user's changes
        # TODO: re-resolve list with latest from backing (to implement refresh()
        # and in case a new model comes in e.g. a search result)

        if self._entity_list is None:
            self._entity_list = []

            # populate attributes
            if model is not None:
                for attr_model in model.attributes:
                    assert attr_model.note_id

                    # only consider owned attributes
                    if attr_model.note_id == self._note.note_id:
                        # create attribute object from model
                        attr: attribute.BaseAttribute = (
                            attribute.BaseAttribute._from_model(
                                attr_model,
                                session=self._note._session,
                                owning_note=self._note,
                            )
                        )

                        self._entity_list.append(attr)

            # sort list by position
            self._entity_list.sort(key=lambda x: x._position)

    def _create_attribute(self, name: str, value_spec: ValueSpec):
        value, kwargs = normalize_value_spec(value_spec)

        if isinstance(value, note.Note):
            # create relation
            attr = relation.Relation(
                name, value, **kwargs, session=self._note._session
            )
        else:
            # create label
            assert type(value) is str
            attr = label.Label(
                name, value, **kwargs, session=self._note._session
            )

        return attr


class InheritedAttributes(NoteStatefulExtension, NameMap, Sequence):
    """
    Interface to a note's inherited attributes.

    :raises ReadOnlyError: Upon attempt to modify
    """

    _list: list[BaseAttribute] = None

    def __len__(self) -> int:
        return len(self._list)

    def __setitem__(self, key: str | int, value: Any):
        raise ReadOnlyError(
            f"Attempt to set inherited attribute at key {key} of {self._note}"
        )

    def __delitem__(self, key: str | int):
        raise ReadOnlyError(
            f"Attempt to delete inherited attribute at key {key} of {self._note}"
        )

    def __iter__(self) -> Iterator[BaseAttribute]:
        return iter(self._list)

    def _setattr(self, value: Any):
        raise ReadOnlyError(
            f"Attempt to set inherited attributes of {self._note}"
        )

    def _setup(self, model: EtapiNoteModel | None):
        # init list every time: unlike owned attributes, no need to preserve
        # local version which may have changes

        if model is None:
            self._list = []
        else:
            inherited_list = []

            for attr_model in model.attributes:
                assert attr_model.note_id

                # only consider inherited attributes
                if attr_model.note_id != self._note._entity_id:
                    owning_note = note.Note._from_id(
                        attr_model.note_id, session=self._note._session
                    )

                    # create attribute object from model
                    attr: attribute.BaseAttribute = (
                        attribute.BaseAttribute._from_model(
                            attr_model,
                            session=self._note._session,
                            owning_note=owning_note,
                        )
                    )

                    inherited_list.append(attr)

            # group by note id
            note_ids = OrderedDict()
            for attr in inherited_list:
                if attr.note.note_id not in note_ids:
                    note_ids[attr.note.note_id] = list()

                note_ids[attr.note.note_id].append(attr)

            # generate sorted list
            list_sorted = list()
            for note_id in note_ids:
                note_ids[note_id].sort(key=lambda x: x._position)
                list_sorted += note_ids[note_id]

            self._list = list_sorted

    def _teardown(self):
        self._list = None


class Attributes(
    NoteExtension, NameMap, MutableSequence[attribute.BaseAttribute]
):
    """
    Interface to a note's owned and inherited attributes.

    This object is stateless; {obj}`Note.attributes.owned` and
    {obj}`Note.attributes.inherited` are the sources of truth
    for owned and inherited attributes respectively.

    For type-safe accesses, use {obj}`Note.labels` or {obj}`Note.relations`.
    """

    _owned: OwnedAttributes
    _inherited: InheritedAttributes

    def __init__(self, note):
        super().__init__(note)

        self._owned = OwnedAttributes(note)
        self._inherited = InheritedAttributes(note)

    @require_setup_prop
    @property
    def owned(self) -> OwnedAttributes:
        """
        Getter/setter for owned attributes.
        Same interface as {obj}`Note.attributes` but filtered by
        owned attributes.
        """
        return self._owned

    @owned.setter
    def owned(self, val: list[BaseAttribute]):
        self._owned._setattr(val)

    @require_setup_prop
    @property
    def inherited(self) -> InheritedAttributes:
        """
        Getter for inherited attributes.
        Same interface as {obj}`Note.attributes` but filtered by
        inherited attributes.
        """
        return self._inherited

    def _setattr(self, val: list[BaseAttribute]):
        # invoke _setattr of owned
        self.owned = val

    @property
    def _combined(self) -> list[BaseAttribute]:
        """
        Get a combined list of owned and inherited attributes.
        """
        return list(self._owned) + list(self._inherited)

    def __setitem__(self, key: str | int, value_spec: ValueSpec):
        """
        Create or update attribute with provided name.
        """
        # invoke __setitem__ of owned
        self._owned[key] = value_spec

    def __delitem__(self, name: str):
        """
        Delete all owned attributes with provided name.
        """
        del self._owned[name]

    def __iter__(self) -> Iterator[BaseAttribute]:
        return iter(self._combined)

    def __len__(self):
        return len(self._owned) + len(self._inherited)

    def insert(self, i: int, value: BaseAttribute):
        # need to offset by inherited length since item will be inserted
        # at len()
        i -= len(self._inherited)
        assert i >= 0

        self._owned.insert(i, value)


class BaseFilteredAttributes[AttributeT: BaseAttribute]:
    """
    Base class to represent attributes filtered by type, with capability to
    further filter by name.
    """

    _note: note.Note
    _filter_cls: type[AttributeT]

    def __init__(self, note: note.Note):
        self._note = note

    def filter_name(self, name: str) -> list[AttributeT]:
        """
        Get attributes filtered by name.
        """
        return [a for a in self._attr_list if a.name == name]

    def _filter_list(self, attrs: list[BaseAttribute]) -> list[AttributeT]:
        return [a for a in attrs if isinstance(a, self._filter_cls)]

    @property
    def _attr_list(self) -> list[AttributeT]:
        ...

    def __getitem__(self, i: int) -> AttributeT:
        return self._attr_list[i]

    def __len__(self):
        return len(self._attr_list)


class BaseOwnedFilteredAttributes[AttributeT: BaseAttribute](
    BaseFilteredAttributes[AttributeT], MutableSequence[AttributeT]
):
    @property
    def _attr_list(self) -> list[AttributeT]:
        return self._filter_list(list(self._note.attributes.owned))

    def __setitem__(self, i: int, val: AttributeT):
        attr = self._attr_list[i]
        index = self._note.attributes.owned.index(attr)

        self._note.attributes.owned[index] = val

    def __delitem__(self, i: int):
        attr = self._attr_list[i]
        attr.delete()

    def insert(self, i: int, val: AttributeT):
        attr = self._attr_list[i]
        index = self._note.attributes.owned.index(attr)

        self._note.attributes.owned.insert(index, val)


class BaseInheritedFilteredAttributes[AttributeT: BaseAttribute](
    BaseFilteredAttributes[AttributeT], Sequence[AttributeT]
):
    @property
    def _attr_list(self) -> list[AttributeT]:
        return self._filter_list(list(self._note.attributes.inherited))


class BaseCombinedFilteredAttributes[AttributeT: BaseAttribute](
    BaseFilteredAttributes[AttributeT], Sequence[AttributeT]
):
    @property
    def _attr_list(self) -> list[AttributeT]:
        return self._filter_list(
            list(self._note.attributes.owned)
            + list(self._note.attributes.inherited)
        )


class OwnedLabels(BaseOwnedFilteredAttributes[label.Label]):
    """
    Accessor for owned labels.
    """

    _filter_cls = label.Label


class InheritedLabels(BaseInheritedFilteredAttributes[label.Label]):
    """
    Accessor for inherited labels.
    """

    _filter_cls = label.Label


class Labels(BaseCombinedFilteredAttributes[label.Label]):
    """
    Accessor for labels, filtered by owned vs inherited.
    """

    _filter_cls = label.Label

    _owned: OwnedLabels
    _inherited: InheritedLabels

    def __init__(self, note: note.Note):
        super().__init__(note)

        self._owned = OwnedLabels(note)
        self._inherited = InheritedLabels(note)

    @property
    def owned(self) -> OwnedLabels:
        return self._owned

    @property
    def inherited(self) -> InheritedLabels:
        return self._inherited


class OwnedRelations(BaseOwnedFilteredAttributes[relation.Relation]):
    """
    Accessor for owned relations.
    """

    _filter_cls = relation.Relation


class InheritedRelations(BaseInheritedFilteredAttributes[relation.Relation]):
    """
    Accessor for inherited relations.
    """

    _filter_cls = relation.Relation


class Relations(BaseCombinedFilteredAttributes[relation.Relation]):
    """
    Accessor for relations, filtered by owned vs inherited.
    """

    _filter_cls = relation.Relation

    _owned: OwnedRelations
    _inherited: InheritedRelations

    def __init__(self, note: note.Note):
        super().__init__(note)

        self._owned = OwnedRelations(note)
        self._inherited = InheritedRelations(note)

    @property
    def owned(self) -> OwnedRelations:
        return self._owned

    @property
    def inherited(self) -> InheritedRelations:
        return self._inherited


def normalize_value_spec(
    value_spec: ValueSpec,
) -> tuple[str | note.Note, dict[str, Any]]:
    """
    Normalize value_spec to tuple of:
    - value (str for Label, Note for Relation)
    - attribute kwargs
    """

    if type(value_spec) is tuple:
        value, kwargs = value_spec
    else:
        value = value_spec
        kwargs = dict()

    return value, kwargs
