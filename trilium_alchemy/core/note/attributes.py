from __future__ import annotations

from collections import OrderedDict
from collections.abc import MutableSequence, Sequence
from typing import Any, Iterator, Type, TypeVar, get_args, get_origin

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


class BaseFilteredAttributes[AttributeT: BaseAttribute]:
    """
    Base class to represent attributes filtered by type, with capability to
    further filter by name.
    """

    _filter_cls: type[AttributeT]

    def __init_subclass__(cls: type[BaseFilteredAttributes]):
        """
        Set _filter_cls based on the type parameter.
        """

        def recurse(
            cls: type[BaseFilteredAttributes],
        ) -> type[AttributeT] | None:
            filter_cls: type[AttributeT] | None = None
            orig_bases: tuple[type] | None = None

            try:
                orig_bases = cls.__orig_bases__
            except AttributeError:
                pass

            if orig_bases is None:
                return None

            for base in orig_bases:
                origin = get_origin(base)

                if origin is None:
                    continue

                if issubclass(origin, BaseFilteredAttributes):
                    args = get_args(base)
                    assert len(args) > 0

                    if isinstance(args[0], TypeVar):
                        # have a TypeVar, look up its bound
                        type_var = args[0]
                        assert type_var.__bound__ is not None
                        filter_cls = type_var.__bound__
                    else:
                        # already have a class
                        filter_cls = args[0]
                else:
                    filter_cls = recurse(base)

                if filter_cls:
                    return filter_cls

        filter_cls = recurse(cls)

        assert filter_cls is not None, f"Failed to get filter_cls for {cls}"
        assert issubclass(filter_cls, BaseAttribute)

        cls._filter_cls = filter_cls

    def __iter__(self) -> Iterator[AttributeT]:
        return iter(self._attr_list)

    def __len__(self) -> int:
        return len(self._attr_list)

    def __getitem__(self, i: int) -> AttributeT:
        return self._attr_list[i]

    def get_first(self, name: str) -> AttributeT | None:
        """
        Get first attribute with provided name, or `None`.
        """
        for a in self._attr_list:
            if a.name == name:
                return a
        return None

    def get_all(self, name: str) -> list[AttributeT]:
        """
        Get all attributes with provided name.
        """
        return [a for a in self._attr_list if a.name == name]

    # TODO: take val type
    """
    def get_value(self, name: str) -> ValT | None:
        pass
        
    def get_values(self, name: str) -> list[ValT]:
        pass

    def set_value(self, name: str, val: ValT):
        ...

    def set_values(self, name: str, vals: list[ValT]):
        ...
    """

    def _filter_list(self, attrs: list[BaseAttribute]) -> list[AttributeT]:
        return [a for a in attrs if isinstance(a, self._filter_cls)]

    @property
    def _attr_list(self) -> list[AttributeT]:
        """
        Overridden by subclass.
        """
        ...

    @property
    def _note_getter(self) -> note.Note:
        """
        Overridden by subclass.
        """
        ...


class BaseDerivedFilteredAttributes[AttributeT: BaseAttribute](
    BaseFilteredAttributes[AttributeT]
):
    _note_obj: note.Note

    def __init__(self, note: note.Note):
        self._note_obj = note

    @property
    def _note_getter(self) -> note.Note:
        return self._note_obj


class BaseOwnedFilteredAttributes[AttributeT: BaseAttribute](
    BaseDerivedFilteredAttributes[AttributeT], MutableSequence[AttributeT]
):
    @property
    def _attr_list(self) -> list[AttributeT]:
        return self._filter_list(list(self._note_getter.attributes.owned))

    def __setitem__(self, i: int, val: AttributeT):
        attr = self._attr_list[i]
        index = self._note_getter.attributes.owned.index(attr)

        self._note_getter.attributes.owned[index] = val

    def __delitem__(self, i: int):
        attr = self._attr_list[i]
        attr.delete()

    def insert(self, i: int, val: AttributeT):
        attr = self._attr_list[i]
        index = self._note_getter.attributes.owned.index(attr)

        self._note_getter.attributes.owned.insert(index, val)


class BaseInheritedFilteredAttributes[AttributeT: BaseAttribute](
    BaseDerivedFilteredAttributes[AttributeT], Sequence[AttributeT]
):
    @property
    def _attr_list(self) -> list[AttributeT]:
        return self._filter_list(list(self._note_getter.attributes.inherited))


class BaseCombinedFilteredAttributes[AttributeT: BaseAttribute](
    BaseDerivedFilteredAttributes[AttributeT], Sequence[AttributeT]
):
    @property
    def _attr_list(self) -> list[AttributeT]:
        return self._filter_list(
            list(self._note_getter.attributes.owned)
            + list(self._note_getter.attributes.inherited)
        )


class OwnedAttributes(
    BaseFilteredAttributes[attribute.BaseAttribute],
    BaseEntityList[attribute.BaseAttribute],
):
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

    @property
    def _note_getter(self) -> note.Note:
        return self._note

    @property
    def _attr_list(self) -> list[attribute.BaseAttribute]:
        assert self._entity_list is not None
        return self._entity_list

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
                    if attr_model.note_id == self._note_getter.note_id:
                        # create attribute object from model
                        attr: attribute.BaseAttribute = (
                            attribute.BaseAttribute._from_model(
                                attr_model,
                                session=self._note_getter._session,
                                owning_note=self._note_getter,
                            )
                        )

                        self._entity_list.append(attr)

            # sort list by position
            self._entity_list.sort(key=lambda x: x._position)


class InheritedAttributes(
    NoteStatefulExtension,
    BaseFilteredAttributes[attribute.BaseAttribute],
    Sequence[attribute.BaseAttribute],
):
    """
    Interface to a note's inherited attributes.

    :raises ReadOnlyError: Upon attempt to modify
    """

    _list: list[BaseAttribute] = None

    @property
    def _attr_list(self) -> list[attribute.BaseAttribute]:
        assert self._list is not None
        return self._list

    @property
    def _note_getter(self) -> note.Note:
        return self._note

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
    NoteExtension,
    BaseFilteredAttributes[attribute.BaseAttribute],
    MutableSequence[attribute.BaseAttribute],
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

    def __setitem__(self, i: int, value_spec: ValueSpec):
        self._owned[i] = value_spec

    def __delitem__(self, i: int):
        del self._owned[i]

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

    @property
    def _attr_list(self) -> list[attribute.BaseAttribute]:
        return list(self._owned) + list(self._inherited)

    def _setattr(self, val: list[BaseAttribute]):
        # invoke _setattr of owned
        self.owned = val

    def insert(self, i: int, value: BaseAttribute):
        # need to offset by inherited length since item will be inserted
        # at len()
        i -= len(self._inherited)
        assert i >= 0

        self._owned.insert(i, value)


class OwnedLabels(BaseOwnedFilteredAttributes[label.Label]):
    """
    Accessor for owned labels.
    """


class InheritedLabels(BaseInheritedFilteredAttributes[label.Label]):
    """
    Accessor for inherited labels.
    """


class Labels(BaseCombinedFilteredAttributes[label.Label]):
    """
    Accessor for labels, filtered by owned vs inherited.
    """

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


class InheritedRelations(BaseInheritedFilteredAttributes[relation.Relation]):
    """
    Accessor for inherited relations.
    """


class Relations(BaseCombinedFilteredAttributes[relation.Relation]):
    """
    Accessor for relations, filtered by owned vs inherited.
    """

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
