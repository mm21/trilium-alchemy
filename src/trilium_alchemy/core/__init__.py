"""
This module implements ORM access to Trilium and fundamental note capabilities.

See the {ref}`user-guide` for a detailed walkthrough with examples.
"""

from pyrollup import rollup

from . import attribute, branch, declarative, entity, exceptions, note, session
from .attribute import *  # noqa
from .branch import *  # noqa
from .declarative import *  # noqa
from .entity import *  # noqa
from .exceptions import *  # noqa
from .note import *  # noqa
from .session import *  # noqa

__all__ = rollup(
    session,
    note,
    attribute,
    branch,
    declarative,
    entity,
    exceptions,
)

__canonical_children__ = [
    "session",
    "note",
    "attribute",
    "branch",
    "declarative",
    "entity",
    "exceptions",
]
