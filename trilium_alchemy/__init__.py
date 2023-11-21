"""
TriliumAlchemy: an SDK and CLI toolkit for Trilium Notes.
"""

from pyrollup import rollup

from .core import *
from .ext import *
from .sync import *

from . import core
from . import sync

__all__ = rollup(core, ext, sync)

__canonical_children__ = [
    "core",
    "ext",
    "sync",
]
