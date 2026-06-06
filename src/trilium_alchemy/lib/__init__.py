"""
Library which builds upon {obj}`BaseDeclarativeNote` to facilitate 
development of note hierarchies and extensions encapsulated in a Python 
package.
"""

from pyrollup import rollup

from . import extension_types, note_types, system_types
from .extension_types import *  # noqa
from .note_types import *  # noqa
from .system_types import *  # noqa

__all__ = rollup(
    note_types,
    extension_types,
    system_types,
)

__canonical_children__ = [
    "note_types",
    "extension_types",
    "system_types",
]
