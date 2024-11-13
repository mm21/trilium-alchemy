"""
Builds upon {obj}`BaseDeclarativeNote` to streamline Trilium extension 
development.
"""

from pyrollup import rollup

from . import helpers, types
from .helpers import *  # noqa
from .types import *  # noqa

__all__ = rollup(
    types,
    helpers,
)

__canonical_children__ = [
    "types",
    "helpers",
]
