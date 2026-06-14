from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from trilium_client.models.note import Note as EtapiNoteModel

from ...attribute.attribute import BaseAttribute
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
        if self._entity_list is not None:
            return
        self._entity_list = []

        if model is None:
            return
        assert model.attributes is not None

        for attr_model in model.attributes:
            assert attr_model.note_id

            # only consider owned attributes
            if attr_model.note_id != self._note_getter.note_id:
                continue

            attr = BaseAttribute._from_model(
                attr_model,
                session=self._note_getter._session,
                owning_note=self._note_getter,
            )
            self._entity_list.append(attr)

        self._entity_list.sort(key=lambda e: e._position)


class InheritedAttributes(
    NoteStatefulExtension,
    BaseFilteredAttributes[BaseAttribute],
    Sequence[BaseAttribute],
):
    """
    Interface to a note's inherited attributes.

    :raises ReadOnlyError: Upon attempt to modify
    """

    _entity_list: list[BaseAttribute] | None = None

    @property
    def _attr_list(self) -> list[BaseAttribute]:
        assert self._entity_list is not None
        return self._entity_list

    @property
    def _note_getter(self) -> Note:
        return self._note

    def _setattr(self, obj: Any):
        _ = obj
        raise ReadOnlyError("attributes.inherited", self._entity)

    def _setup(self, model: EtapiNoteModel | None):
        from ..note import Note

        if self._entity_list is not None:
            return
        self._entity_list = []

        if model is None:
            return
        assert model.attributes is not None

        attr_map: dict[str, list[BaseAttribute]] = defaultdict(list)
        for attr_model in model.attributes:
            assert attr_model.note_id

            # only consider inherited attributes
            if attr_model.note_id == self._note._entity_id:
                continue

            owning_note = Note._from_id(attr_model.note_id, session=self._note._session)
            attr = BaseAttribute._from_model(
                attr_model,
                session=self._note._session,
                owning_note=owning_note,
            )
            attr_map[attr_model.note_id].append(attr)

        for note_id in sorted(attr_map.keys()):
            self._entity_list += sorted(attr_map[note_id], key=lambda a: a._position)

    def _teardown(self):
        self._entity_list = None


class Attributes(
    NoteExtension,
    BaseFilteredAttributes[BaseAttribute],
    Sequence[BaseAttribute],
):
    """
    Interface to a note's owned and inherited attributes.

    This object is stateless; {obj}`Note.attributes.owned` and
    {obj}`Note.attributes.inherited` are the sources of truth for owned and inherited
    attributes respectively.

    For type-safe accesses, use {obj}`Note.labels` or {obj}`Note.relations`.

    :raises ReadOnlyError: Upon attempt to modify
    """

    _owned: OwnedAttributes
    _inherited: InheritedAttributes

    def __init__(self, note: Note):
        super().__init__(note)

        self._owned = OwnedAttributes(note)
        self._inherited = InheritedAttributes(note)

    @property
    def owned(self) -> OwnedAttributes:
        """
        Getter/setter for owned attributes.

        Same interface as {obj}`Note.attributes` but filtered by owned attributes.
        """
        self._model.setup_check()
        return self._owned

    @owned.setter
    def owned(self, val: Sequence[BaseAttribute]):
        self._owned._setattr(val)

    @property
    def inherited(self) -> InheritedAttributes:
        """
        Getter for inherited attributes.

        Same interface as {obj}`Note.attributes` but filtered by inherited attributes.
        """
        self._model.setup_check()
        return self._inherited

    @property
    def _attr_list(self) -> list[BaseAttribute]:
        return list(self._owned) + list(self._inherited)

    @property
    def _note_getter(self) -> Note:
        return self._note

    def _setattr(self, obj: list[BaseAttribute]):
        _ = obj
        raise ReadOnlyError("attributes", self._entity)
