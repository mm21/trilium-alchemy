from enum import Enum, auto


class State(Enum):
    """
    Entity state. Maintained automatically based on the user's
    updates and object's current state in Trilium.

    For example, state will change from {obj}`State.UPDATE` back
    to {obj}`State.CLEAN` if the user reverts changes.
    """

    CLEAN = auto()
    """No pending changes"""

    CREATE = auto()
    """Pending create"""

    UPDATE = auto()
    """Pending update"""

    DELETE = auto()
    """Pending delete"""
