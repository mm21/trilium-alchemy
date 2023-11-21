from pyrollup import rollup

from .attribute import *
from .label import *
from .relation import *

from . import attribute
from . import label
from . import relation

__all__ = rollup(
    attribute,
    label,
    relation,
)

__canonical_syms__ = __all__
