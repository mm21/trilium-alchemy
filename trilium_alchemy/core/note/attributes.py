from __future__ import annotations

from typing import overload, TypeVar, Generic, Type, Hashable, Any

from pprint import pformat

from collections import OrderedDict
from collections.abc import (
    MutableSequence,
    Sequence,
    MutableSet,
    MutableMapping,
)
from abc import ABC, abstractmethod

from trilium_client.models.note import Note as EtapiNoteModel
from trilium_client.models.attribute import Attribute as EtapiAttributeModel

from . import note
from ..exceptions import *
from ..entity import Entity
from ..entity.model import Extension, StatefulExtension, ExtensionDescriptor
from ..attribute import attribute, label, relation
from ..attribute.attribute import Attribute
from .extension import List, NoteExtension, NoteStatefulExtension

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
    def _name_map(self) -> dict[str, list[attribute.Attribute]]:
        attrs = dict()
        for attr in list(self):
            if attr.name in attrs:
                attrs[attr.name].append(attr)
            else:
                attrs[attr.name] = [attr]
        return attrs

    def __getitem__(self, key: str | int):
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

    def __contains__(self, key: str | attribute.Attribute) -> bool:
        """
        This can be invoked by name or by object.
        """

        # check name first, then defer to super to check object
        if key in self._name_map:
            return True
        return super().__contains__(key)


class OwnedAttributes(NameMap, List[attribute.Attribute]):
    """
    Interface to a note's owned attributes. Implements same
    interface as {obj}`Attributes` but accessed as
    `Note.attributes.owned`.
    """

    _child_cls = attribute.Attribute
    _owner_field = "_note"

    def __str__(self):
        if self._entity_list is not None and len(self._entity_list) > 0:
            s = "\n".join([str(e) for e in self._entity_list])
        else:
            s = "No attributes"
        return f"{s}"

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
                    # only consider owned attributes
                    if attr_model.note_id == self._note.note_id:
                        # create attribute object from model
                        attr: attribute.Attribute = (
                            attribute.Attribute._from_model(
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

    def __delitem__(self, key: str):
        """
        Delete all owned attributes with provided name.
        """

        if type(key) is str:
            for attr in list(self):
                if attr.name == key:
                    attr.delete()
        else:
            super().__delitem__(key)

    def __iter__(self):
        yield from self._entity_list


class InheritedAttributes(NoteStatefulExtension, NameMap, Sequence):
    """
    Interface to a note's inherited attributes. Implements same
    interface as {obj}`Attributes` but accessed as
    `Note.attributes.inherited`.

    Raises {obj}`ReadOnlyError` upon attempt to modify.
    """

    _list: list[Attribute] = None

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
                # only consider inherited attributes
                if attr_model.note_id != self._note._entity_id:
                    owning_note = note.Note._from_id(
                        attr_model.note_id, session=self._note._session
                    )

                    # create attribute object from model
                    attr: attribute.Attribute = attribute.Attribute._from_model(
                        attr_model,
                        session=self._note._session,
                        owning_note=owning_note,
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

    def __len__(self):
        return len(self._list)

    def __setitem__(self, key: str | int, value: Any):
        raise ReadOnlyError(
            f"Attempt to set inherited attribute at key {key} of {self._note}"
        )

    def __delitem__(self, key: str | int):
        raise ReadOnlyError(
            f"Attempt to delete inherited attribute at key {key} of {self._note}"
        )

    def __iter__(self):
        yield from self._list


class Attributes(NoteExtension, NameMap, MutableSequence):
    """
    Interface to a note's owned and inherited attributes.

    Access as {obj}`Note.attributes`, a descriptor mapping to
    an instance of this class.

    Access as a list:

    ```
    # add some attributes
    note.attributes.append(Label("myLabel"))
    note.attributes.append(Relation("myRelation", session.root))

    for attr in note.attributes:
        print(f"Attribute: {attr}")
    ```
    ```none
    Attribute: Label(#myLabel, value=, attribute_id=None, note=Note(title=new note, note_id=None), position=10)
    Attribute: Relation(~myRelation, target=Note(title=root, note_id=root), attribute_id=None, note=Note(title=new note, note_id=None), position=20)
    ```

    Index by attribute name, getting a list of attributes with that name:

    ```
    # add a label
    note += Label("myLabel")

    print(note.attributes["myLabel"][0])
    ```
    ```none
    Label(#myLabel, value=, attribute_id=None, note=Note(title=new note, note_id=None), position=10)
    ```

    Use `in`{l=python} to check if an attribute exists by name:

    ```
    assert "myLabel" in note.attributes
    ```

    When an attribute is deleted from the list, it's automatically marked
    for delete:

    ```
    # add a label
    label = Label("myLabel")
    note += label

    # delete from list
    del note.attributes[0]

    print(f"label.state: {label.state}")
    ```
    ```none
    label.state: State.DELETE
    ```

    Assign a new list, deleting any existing attributes not in the list:

    ```
    # add a label
    label1 = Label("myLabel1")
    note += label1

    # assign a new list of attributes
    label2 = Label("myLabel2")
    note.attributes = [label2]

    print(f"label1.state: {label1.state}")
    print(f"label2.state: {label2.state}")
    ```
    ```none
    label1.state: State.DELETE
    label2.state: State.CREATE
    ```

    This object is stateless; {obj}`Note.attributes.owned` and
    {obj}`Note.attributes.inherited` are the sources of truth
    for owned and inherited attributes respectively.

    ```{todo}
    Add `Attributes.labels`, `Attributes.relations` with same interface
    as {obj}`Attributes`, filtered by attribute type
    ```
    """

    owned: OwnedAttributes = ExtensionDescriptor("_owned")
    """
    Same interface as {obj}`Note.attributes` but filtered by
    owned attributes.
    """

    inherited: InheritedAttributes = ExtensionDescriptor("_inherited")
    """
    Same interface as {obj}`Note.attributes` but filtered by
    inherited attributes.
    """

    _owned: OwnedAttributes = None
    _inherited: InheritedAttributes = None

    def __init__(self, note):
        super().__init__(note)

        self._owned = OwnedAttributes(note)
        self._inherited = InheritedAttributes(note)

    def _setattr(self, val: list[Attribute]):
        # invoke _setattr of owned
        self.owned = val

    @property
    def _combined(self) -> list[Attribute]:
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

    def __iter__(self):
        yield from self._combined

    def __len__(self):
        return len(self._owned) + len(self._inherited)

    def insert(self, i: int, value: Any):
        # need to offset by inherited length since item will be inserted
        # at len()
        i -= len(self._inherited)
        assert i >= 0

        self._owned.insert(i, value)


# TODO:
# FilteredAttributes
# - used for Note.labels, Note.relations
# - provides same interface as Attributes but filtered by type
# Labels(FilteredAttributes)
# Relations(FilteredAttributes)


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
