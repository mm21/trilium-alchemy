from __future__ import annotations

from typing import overload, TypeVar, Generic, Type, Hashable

from trilium_client.models.attribute import Attribute as EtapiAttributeModel

from ..exceptions import _assert_validate
from ..session import Session, require_session
from .. import note

from ..entity import Entity
from ..entity.model import WriteThroughDescriptor, require_model

from .attribute import Attribute

__all__ = [
    "Relation",
]


class Relation(Attribute):
    """
    Encapsulates a relation.

    Once instantiated, the relation needs to be added to a {obj}`Note`.
    See the documentation of {obj}`Note.attributes` for details.
    """

    # set _target, then populate model's value with the target's note_id
    target: note.Note = WriteThroughDescriptor("_target", "note_id", "value")
    """
    Target note of this relation.
    """

    attribute_type: str = "relation"

    _target: note.Note = None

    @require_session
    @require_model
    def __init__(
        self,
        name: str,
        target: note.Note,
        inheritable: bool = False,
        session: Session | None = None,
        **kwargs,
    ):
        """
        :param name: Relation name
        :param target: Target note
        :param inheritable: Whether attribute is inherited to children
        :param session: Session, or `None`{l=python} to use default
        """

        model_backing = kwargs["model_backing"]

        super().__init__(
            name,
            inheritable=inheritable,
            session=session,
            **kwargs,
        )

        # set target if not getting from database
        if model_backing is None:
            self.target = target

    @property
    def _str_short(self):
        return f"Relation(~{self.name}, target={self.target}, attribute_id={self.attribute_id}, note={self.note}, position={self.position})"

    @property
    def _str_safe(self):
        return f"Relation(attribute_id={self._entity_id}, id={id(self)})"

    def _setup(self, model: EtapiAttributeModel):
        super()._setup(model)

        assert model.value is not None
        assert model.value != ""

        # setup target
        self._target = note.Note(note_id=model.value, session=self._session)

    def _flush_check(self):
        _assert_validate(isinstance(self._target, note.Note))

    def _flush_prep(self):
        """
        Set target note_id if target is being newly created and didn't have a
        note_id before.

        If this is the case, 'value' field will be None. This should
        automatically maintain dirty state correctly since any existing value
        can't be None.
        """
        assert self._target.note_id is not None

        if self._model.get_field("value") is None:
            self._model.set_field("value", self._target.note_id)
        else:
            assert self._model.get_field("value") == self._target.note_id

    @property
    def _dependencies(self) -> set[Entity]:
        """
        Relation also depends on target note.
        """
        return super()._dependencies | {self._target}
