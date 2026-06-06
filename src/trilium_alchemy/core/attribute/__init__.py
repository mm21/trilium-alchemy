from pyrollup import rollup

from . import attribute, label, relation
from .attribute import *  # noqa
from .label import *  # noqa
from .relation import *  # noqa

__all__ = rollup(
    attribute,
    label,
    relation,
)

__canonical_syms__ = __all__
