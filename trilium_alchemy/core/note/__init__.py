from pyrollup import rollup

from . import note
from .note import *  # noqa

__all__ = rollup(note)
__canonical_syms__ = __all__
__canonical_children__ = [
    "attributes",
    "branches",
    "content",
]
