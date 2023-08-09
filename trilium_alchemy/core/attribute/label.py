from __future__ import annotations

from typing import overload, TypeVar, Generic, Type, Hashable

from ..exceptions import *
from ..session import Session, require_session
from .. import note

from ..entity.model import FieldDescriptor, require_model

from .attribute import Attribute

__all__ = [
    "Label",
]


class Label(Attribute):
    """
    Encapsulates a label.

    Once instantiated, the label needs to be added to a {obj}`Note`.
    See the documentation of {obj}`Note.attributes` for details.
    """

    value: str = FieldDescriptor("value")
    """Label value, or empty string"""

    attribute_type: str = "label"

    @require_session
    @require_model
    def __init__(
        self,
        name: str,
        value: str = "",
        inheritable: bool = False,
        session: Session = None,
        **kwargs,
    ):
        """
        :param name: Label name
        :param value: Label value, or empty string
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

        # set value if not getting from database
        if model_backing is None:
            self.value = value

    @property
    def _str_short(self):
        return f"Label(#{self.name}, value={self.value}, attribute_id={self.attribute_id}, note={self.note}, position={self.position})"

    @property
    def _str_safe(self):
        return f"Label(attribute_id={self._entity_id}, id={id(self)})"
