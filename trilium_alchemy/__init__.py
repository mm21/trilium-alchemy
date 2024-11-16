"""
TriliumAlchemy: an SDK and CLI toolkit for Trilium Notes.
"""

from pyrollup import rollup

from . import core, lib, tools
from .core import *  # noqa
from .lib import *  # noqa
from .tools import *  # noqa

__all__ = rollup(core, lib, tools)

__canonical_children__ = [
    "core",
    "lib",
    "tools",
]
