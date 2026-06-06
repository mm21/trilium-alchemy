"""
TriliumAlchemy: an SDK and CLI toolkit for Trilium Notes.
"""

from pyrollup import rollup

from . import core, lib
from .core import *  # noqa
from .lib import *  # noqa

__all__ = rollup(core, lib)

__canonical_children__ = [
    "core",
    "lib",
]
