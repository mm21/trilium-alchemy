__submodules__ = [
    "labels",
    "relations",
    "attributes",
]
__canonical_children__ = []

# isort: off
# <AUTOGEN_INIT>
from .labels import (
    Labels,
    OwnedLabels,
    InheritedLabels,
)
from .relations import (
    Relations,
    OwnedRelations,
    InheritedRelations,
)
from .attributes import (
    Attributes,
    OwnedAttributes,
    InheritedAttributes,
)

__all__ = [
    "Labels",
    "OwnedLabels",
    "InheritedLabels",
    "Relations",
    "OwnedRelations",
    "InheritedRelations",
    "Attributes",
    "OwnedAttributes",
    "InheritedAttributes",
]
# </AUTOGEN_INIT>

__canonical_syms__ = __all__
