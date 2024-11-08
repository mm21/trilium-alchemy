from __future__ import annotations

from typing import TYPE_CHECKING

from ...attribute import relation
from ._filters import (
    AttributeListMixin,
    BaseCombinedFilteredAttributes,
    BaseInheritedFilteredAttributes,
    BaseOwnedFilteredAttributes,
)

if TYPE_CHECKING:
    from ..note import Note

__all__ = [
    "Relations",
]


class BaseReadableRelationMixin(AttributeListMixin[relation.Relation]):
    def get_value(self, name: str) -> relation.Relation | None:
        """
        Get value of first relation with provided name.
        """
        attr = self.get(name)
        return None if attr is None else attr.target

    def get_values(self, name: str) -> list[Note]:
        """
        Get values of all relations with provided name.
        """
        return [attr.target for attr in self.get_all(name)]


class BaseWriteableRelationMixin(BaseReadableRelationMixin):
    _value_name = "target"

    def set_value(self, name: str, val: Note, inheritable: bool = False):
        """
        Set value of first relation with provided name.
        """
        self._set_value(name, val, inheritable)

    def set_values(
        self, name: str, vals: list[Note], inheritable: bool = False
    ):
        """
        Set values of all relations with provided name, creating or deleting
        relations as necessary.
        """
        self._set_values(name, vals, inheritable)

    def append_value(self, name: str, val: Note, inheritable: bool = False):
        """
        Create and append new relation.
        """
        self._append_value(name, val, inheritable)

    def _create_attr(self, name: str) -> relation.Relation:
        attr = relation.Relation(name, session=self._note_getter.session)
        self._note_getter.attributes.owned.append(attr)
        return attr


class OwnedRelations(
    BaseOwnedFilteredAttributes[relation.Relation], BaseWriteableRelationMixin
):
    """
    Accessor for owned relations.
    """


class InheritedRelations(
    BaseInheritedFilteredAttributes[relation.Relation],
    BaseReadableRelationMixin,
):
    """
    Accessor for inherited relations.
    """


class Relations(
    BaseCombinedFilteredAttributes[relation.Relation],
    BaseWriteableRelationMixin,
):
    """
    Accessor for relations, filtered by owned vs inherited.
    """

    _owned: OwnedRelations
    _inherited: InheritedRelations

    def __init__(self, note: Note):
        super().__init__(note)

        self._owned = OwnedRelations(note)
        self._inherited = InheritedRelations(note)

    @property
    def owned(self) -> OwnedRelations:
        return self._owned

    @owned.setter
    def owned(self, val: OwnedRelations):
        assert val is self._owned

    @property
    def inherited(self) -> InheritedRelations:
        return self._inherited
