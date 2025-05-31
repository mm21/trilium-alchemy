from __future__ import annotations

from typing import TYPE_CHECKING

from ...attribute import label
from ._filters import (
    AttributeListMixin,
    BaseCombinedFilteredAttributes,
    BaseInheritedFilteredAttributes,
    BaseOwnedFilteredAttributes,
)

if TYPE_CHECKING:
    from ..note import Note

__all__ = [
    "Labels",
    "OwnedLabels",
    "InheritedLabels",
]


class BaseReadableLabelMixin(AttributeListMixin[label.Label]):
    def get_value(self, name: str) -> str | None:
        """
        Get value of first label with provided name.
        """
        attr = self.get(name)
        return None if attr is None else attr.value

    def get_values(self, name: str) -> list[str]:
        """
        Get values of all labels with provided name.
        """
        return [attr.value for attr in self.get_all(name)]


class BaseWriteableLabelMixin(BaseReadableLabelMixin):
    _value_name = "value"

    def set_value(self, name: str, val: str, inheritable: bool = False):
        """
        Set value of first label with provided name, creating if it doesn't
        exist.
        """
        self._set_value(name, val, inheritable)

    def set_values(self, name: str, vals: list[str], inheritable: bool = False):
        """
        Set values of all labels with provided name, creating or deleting
        labels as necessary.
        """
        self._set_values(name, vals, inheritable)

    def append_value(self, name: str, val: str = "", inheritable: bool = False):
        """
        Create and append new label.
        """
        self._append_value(name, val, inheritable)

    def _create_attr(self, name: str) -> label.Label:
        attr = label.Label(name, session=self._note_getter.session)
        self._note_getter.attributes.owned.append(attr)
        return attr


class OwnedLabels(
    BaseOwnedFilteredAttributes[label.Label], BaseWriteableLabelMixin
):
    """
    Accessor for owned labels.
    """


class InheritedLabels(
    BaseInheritedFilteredAttributes[label.Label], BaseReadableLabelMixin
):
    """
    Accessor for inherited labels.
    """


class Labels(
    BaseCombinedFilteredAttributes[label.Label],
    BaseWriteableLabelMixin,
):
    """
    Accessor for labels, filtered by owned vs inherited.
    """

    _owned: OwnedLabels
    _inherited: InheritedLabels

    def __init__(self, note: Note):
        super().__init__(note)

        self._owned = OwnedLabels(note)
        self._inherited = InheritedLabels(note)

    @property
    def owned(self) -> OwnedLabels:
        return self._owned

    @owned.setter
    def owned(self, val: OwnedLabels):
        assert val is self._owned

    @property
    def inherited(self) -> InheritedLabels:
        return self._inherited
