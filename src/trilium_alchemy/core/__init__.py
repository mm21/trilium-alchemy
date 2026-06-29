"""
This module implements ORM access to Trilium and fundamental note capabilities.

See the {ref}`user-guide` for a detailed walkthrough with examples.
"""

__submodules__ = {
    "session": None,
    "note": None,
    "branch": None,
    "attribute": ["Label", "Relation"],
    "declarative": None,
    "exceptions": None,
    "entity": ["State"],
}
__canonical_children__ = [k for k in __submodules__.keys()]

# isort: off
# <AUTOGEN_INIT>
from .session import (
    Session,
)
from .note import (
    Note,
    Attachment,
)
from .branch import (
    Branch,
)
from .attribute import (
    Label,
    Relation,
)
from .declarative import (
    BaseDeclarativeNote,
    BaseDeclarativeMixin,
    label,
    relation,
    label_def,
    relation_def,
    children,
    child,
)
from .exceptions import (
    ReadOnlyError,
    ValidationError,
)
from .entity import (
    State,
)

__all__ = [
    "Session",
    "Note",
    "Attachment",
    "Branch",
    "Label",
    "Relation",
    "BaseDeclarativeNote",
    "BaseDeclarativeMixin",
    "label",
    "relation",
    "label_def",
    "relation_def",
    "children",
    "child",
    "ReadOnlyError",
    "ValidationError",
    "State",
]
# </AUTOGEN_INIT>
