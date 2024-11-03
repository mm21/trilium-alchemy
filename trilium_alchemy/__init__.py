"""
TriliumAlchemy: an SDK and CLI toolkit for Trilium Notes.
"""

from pyrollup import rollup

from . import core, sync
from .core import *  # noqa
from .ext import *  # noqa
from .sync import *  # noqa

__all__ = rollup(core, ext, sync)

__canonical_children__ = [
    "core",
    "ext",
    "sync",
]
