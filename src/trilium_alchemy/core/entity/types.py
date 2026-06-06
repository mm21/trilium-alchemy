from enum import Enum, auto

from rich.markup import escape


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

    def __str__(self) -> str:
        color_map = {
            State.CLEAN: "cyan",
            State.CREATE: "bright_green",
            State.UPDATE: "bright_yellow",
            State.DELETE: "red",
        }

        start = escape("[")
        end = escape("]")
        return f"{start}[{color_map[self]}]{self.name}[/{color_map[self]}]{end}"
