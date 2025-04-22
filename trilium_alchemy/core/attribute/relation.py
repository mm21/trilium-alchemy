from __future__ import annotations

from typing import TYPE_CHECKING

from trilium_client.models.attribute import Attribute as EtapiAttributeModel

from ..entity.entity import BaseEntity
from ..entity.model import WriteThroughDescriptor
from ..exceptions import _assert_validate
from ..session import Session
from .attribute import BaseAttribute

if TYPE_CHECKING:
    from ..note.note import Note

__all__ = [
    "Relation",
]


class Relation(BaseAttribute):
    """
    Encapsulates a relation.

    Once instantiated, the relation needs to be added to a {obj}`Note`; see
    {ref}`working-with-attributes` for details.
    """

    _attribute_type: str = "relation"

    _target = WriteThroughDescriptor("_target_obj", "note_id", "value")
    _target_obj: Note | None = None

    def __init__(
        self,
        name: str,
        target: Note | None = None,
        inheritable: bool = False,
        session: Session | None = None,
        **kwargs,
    ):
        """
        :param name: Relation name
        :param target: Target note
        :param inheritable: Whether attribute is inherited to children
        :param session: Session, or `None`{l=python} to use default
        :param kwargs: Internal only
        """

        model_backing = kwargs.get("_model_backing")

        super().__init__(
            name,
            inheritable=inheritable,
            session=session,
            **kwargs,
        )

        # set target if provided and not getting from database
        if model_backing is None and target is not None:
            self.target = target

    @property
    def target(self) -> Note:
        """
        Getter/setter for target note, with getter validating that the target
        has already been assigned.
        """
        assert self._target is not None
        return self._target

    @target.setter
    def target(self, target: Note):
        self._target = target

    @property
    def target_raw(self) -> Note | None:
        """
        Getter for target note, or `None` if not yet assigned.
        """
        return self._target

    @property
    def _str_short(self):
        return f"Relation('{self.name}', {self.target_raw}, attribute_id='{self.attribute_id}')"

    @property
    def _str_safe(self):
        return f"Relation(attribute_id={self._entity_id}, id={id(self)})"

    def _setup(self, model: EtapiAttributeModel):
        super()._setup(model)

        assert model.value is not None
        assert model.value != ""

        from ..note.note import Note

        # setup target
        self._target_obj = Note(note_id=model.value, session=self._session)

    def _flush_check(self):
        from ..note.note import Note

        _assert_validate(
            self._target_obj is not None, f"Relation {self} has no target note"
        )
        _assert_validate(isinstance(self._target_obj, Note))

    def _flush_prep(self):
        """
        Set target note_id if target is being newly created and didn't have a
        note_id before.

        If this is the case, 'value' field will be None. This should
        automatically maintain dirty state correctly since any existing value
        can't be None.
        """
        assert self._target_obj is not None

        target_note_id = self._target_obj.note_id
        assert target_note_id is not None

        if not self._model.get_field("value"):
            self._model.set_field("value", target_note_id)
        else:
            assert self._model.get_field("value") == target_note_id

    @property
    def _dependencies(self) -> set[BaseEntity]:
        """
        Relation also depends on target note.
        """
        return super()._dependencies | {self._target}
