"""
This module implements ORM access to Trilium and fundamental note capabilities.

See the {ref}`user-guide` for a detailed walkthrough with examples.
"""

__submodules__ = [
    "session",
    "note",
    "branch",
    "attribute",
    "declarative",
    "exceptions",
    "entity",
]

from .attribute import (
    BaseAttribute,
    Label,
    Relation,
)
from .branch import (
    Branch,
)
from .declarative import (
    BaseDeclarativeMixin,
    BaseDeclarativeNote,
    child,
    children,
    label,
    label_def,
    relation,
    relation_def,
)
from .entity import (
    BaseEntity,
    State,
)
from .exceptions import (
    ReadOnlyError,
    ValidationError,
)
from .note import (
    Attachment,
    Attachments,
    Note,
)

# <AUTOGEN_INIT>
from .session import (
    Session,
)

__all__ = [
    "Session",
    "Note",
    "Attachment",
    "Attachments",
    "Branch",
    "BaseAttribute",
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
    "BaseEntity",
    "State",
]
# </AUTOGEN_INIT>

__canonical_children__ = [
    "session",
    "note",
    "attribute",
    "branch",
    "declarative",
    "entity",
    "exceptions",
]
