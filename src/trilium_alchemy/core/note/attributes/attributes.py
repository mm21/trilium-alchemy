from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from trilium_client.models.note import Note as EtapiNoteModel

from ...attribute.attribute import BaseAttribute
from ...entity.model import require_setup_prop
from ...exceptions import ReadOnlyError
from ..extension import BaseEntityList, NoteExtension, NoteStatefulExtension
from ._filters import BaseFilteredAttributes

if TYPE_CHECKING:
    from ..note import Note

__all__ = [
    "Attributes",
    "OwnedAttributes",
    "InheritedAttributes",
]


class OwnedAttributes(
    BaseFilteredAttributes[BaseAttribute],
    BaseEntityList[BaseAttribute],
):
    """
    Interface to a note's owned attributes.
    """

    _child_cls = BaseAttribute
    _owner_field = "_note"

    def __str__(self):
        if self._entity_list is not None and len(self._entity_list) > 0:
            s = "\n".join([str(e) for e in self._entity_list])
        else:
            s = "No attributes"
        return f"{s}"

    @property
    def _note_getter(self) -> Note:
        return self._note

    @property
    def _attr_list(self) -> list[BaseAttribute]:
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
                        attr: BaseAttribute = BaseAttribute._from_model(
                            attr_model,
                            session=self._note_getter._session,
                            owning_note=self._note_getter,
                        )

                        self._entity_list.append(attr)

            # sort list by position
            self._entity_list.sort(key=lambda x: x._position)


class InheritedAttributes(
    NoteStatefulExtension,
    BaseFilteredAttributes[BaseAttribute],
    Sequence[BaseAttribute],
):
    """
    Interface to a note's inherited attributes.

    :raises ReadOnlyError: Upon attempt to modify
    """

    _list: list[BaseAttribute] = None

    @property
    def _attr_list(self) -> list[BaseAttribute]:
        assert self._list is not None
        return self._list

    @property
    def _note_getter(self) -> Note:
        return self._note

    def _setattr(self, value: Any):
        raise ReadOnlyError

    def _setup(self, model: EtapiNoteModel | None):
        # init list every time: unlike owned attributes, no need to preserve
        # local version which may have changes

        from ..note import Note

        if model is None:
            self._list = []
        else:
            inherited_list = []

            for attr_model in model.attributes:
                assert attr_model.note_id

                # only consider inherited attributes
                if attr_model.note_id != self._note._entity_id:
                    owning_note = Note._from_id(
                        attr_model.note_id, session=self._note._session
                    )

                    # create attribute object from model
                    attr: BaseAttribute = BaseAttribute._from_model(
                        attr_model,
                        session=self._note._session,
                        owning_note=owning_note,
                    )

                    inherited_list.append(attr)

            # group by note id
            attr_map: dict[str, list[BaseAttribute]] = dict()
            for attr in inherited_list:
                if attr.note.note_id not in attr_map:
                    attr_map[attr.note.note_id] = list()

                attr_map[attr.note.note_id].append(attr)

            # generate sorted list
            list_sorted = list()
            for note_id in attr_map:
                attr_map[note_id].sort(key=lambda x: x._position)
                list_sorted += attr_map[note_id]

            self._list = list_sorted

    def _teardown(self):
        self._list = None


class Attributes(
    NoteExtension,
    BaseFilteredAttributes[BaseAttribute],
    Sequence[BaseAttribute],
):
    """
    Interface to a note's owned and inherited attributes.

    This object is stateless; {obj}`Note.attributes.owned` and
    {obj}`Note.attributes.inherited` are the sources of truth
    for owned and inherited attributes respectively.

    For type-safe accesses, use {obj}`Note.labels` or {obj}`Note.relations`.

    :raises ReadOnlyError: Upon attempt to modify
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

    @property
    def _attr_list(self) -> list[BaseAttribute]:
        return list(self._owned) + list(self._inherited)

    def _setattr(self, val: list[BaseAttribute]):
        raise ReadOnlyError
