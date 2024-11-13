from __future__ import annotations

from ..session import Session
from .attribute import BaseAttribute

__all__ = [
    "Label",
]


class Label(BaseAttribute):
    """
    Encapsulates a label.

    Once instantiated, the label needs to be added to a {obj}`Note`; see
    {ref}`working-with-attributes` for details.
    """

    _attribute_type: str = "label"

    def __init__(
        self,
        name: str,
        value: str = "",
        inheritable: bool = False,
        session: Session | None = None,
        **kwargs,
    ):
        """
        :param name: Label name
        :param value: Label value, or empty string
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

        # set value if not getting from database
        if model_backing is None:
            self.value = value

    @property
    def value(self) -> str:
        """
        Getter/setter for label value, which may be an empty string.
        """
        return self._model.get_field("value")

    @value.setter
    def value(self, val: str):
        self._model.set_field("value", val)

    @property
    def _str_short(self):
        return f"Label(#{self.name}, value={self.value}, attribute_id={self.attribute_id}, note={self.note}, position={self.position})"

    @property
    def _str_safe(self):
        return f"Label(attribute_id={self._entity_id}, id={id(self)})"
