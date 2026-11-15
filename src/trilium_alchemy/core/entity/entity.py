from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Self

from alchemizer import BaseEntity as _BaseEntity
from pydantic import BaseModel
from rich.markup import escape

from ..session import Session
from .model import BaseEntityModel
from .types import State

__all__ = [
    "BaseEntity",
]


class BaseEntity[ModelT: BaseEntityModel, EtapiModelT: BaseModel](
    _BaseEntity[Session, ModelT, EtapiModelT], ABC
):
    """
    Base class for Trilium entities.

    Should not be instantiated by user, but published for reference.
    """

    # MTODO: abstract property
    _force_position_cleanup: bool = False

    # NOTE: public interface is inherited, but explicitly defined here with
    # Trilium-specific documentation

    @property
    def state(self) -> State:
        """
        Current state.
        """
        return super().state

    @property
    def session(self) -> Session:
        """
        Session to which this entity belongs.
        """
        return super().session

    @property
    def str_short(self) -> str:
        """
        Get a short description of this entity.
        """
        return super().str_short

    @property
    def str_summary(self) -> str:
        """
        Get a summary of this entity, including its current state and model values.
        """
        return super().str_summary

    def flush(self):
        """
        Commit changes to Trilium for this entity and its dependencies.
        """
        super().flush()

    def invalidate(self):
        """
        Discard cached contents and user-provided data for this object.

        Upon next access, data will be fetched from Trilium.
        """
        super().invalidate()

    def delete(self):
        """
        Mark this entity for pending delete.
        """
        super().delete()

    def refresh(self):
        """
        Update value from Trilium, discarding any local changes.
        """
        super().refresh()

    @classmethod
    def _get_session_cls(cls) -> type[Session]:
        return Session

    @property
    def _str_state(self) -> str:
        color = {
            State.CLEAN: "cyan",
            State.CREATE: "bright_green",
            State.UPDATE: "bright_yellow",
            State.DELETE: "red",
        }[self._state]

        start = escape("[")
        end = escape("]")
        return f"{start}[{color}]{self._state.name}[/{color}]{end}"

    @property
    @abstractmethod
    def _str_safe(self) -> str:
        """
        Return string for debugging and don't invoke model setup.
        """
        ...

    @classmethod
    @abstractmethod
    def _from_id(cls, entity_id: str, session: Session | None = None) -> Self:
        """
        Instantiate this entity from an id.
        """
        ...

    @classmethod
    @abstractmethod
    def _from_model(cls, model: EtapiModelT) -> Self: ...


class PositionMixin(ABC):
    """
    Mixin to indicate that an Entity subclass has a position field.
    """

    @property
    @abstractmethod
    def _position(self) -> int: ...

    @_position.setter
    @abstractmethod
    def _position(self, val: int): ...


# NOTE: this is better suited as an intersection type, not yet supported
# - https://github.com/python/typing/issues/213
# - https://github.com/CarliJoy/intersection_examples/issues/8
class OrderedEntity[ModelT: BaseEntityModel, EtapiModelT: BaseModel](
    BaseEntity[ModelT, EtapiModelT], PositionMixin
):
    pass
