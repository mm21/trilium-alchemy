"""
This module implements ORM access to Trilium and fundamental note capabilities.

Examples in this module assume you have created a {obj}`Session`
and that you will either invoke {obj}`Session.flush` or use a context manager
to commit the changes.

For example:

```
session = Session(HOST, token=TOKEN)

...

session.flush()
```

Or:

```
with Session(HOST, token=TOKEN) as session:
    ...
```
"""

from pyrollup import rollup

from .session import *
from .note import *
from .attribute import *
from .branch import *
from .declarative import *
from .exceptions import *
from .entity import *

from . import session
from . import note
from . import attribute
from . import branch
from . import declarative
from . import entity
from . import exceptions

__all__ = rollup(
    session,
    note,
    attribute,
    branch,
    declarative,
    entity,
    exceptions,
)

__canonical_syms__ = [
    "Session",
]

__canonical_children__ = [
    "note",
    "attribute",
    "branch",
    "declarative",
    "entity",
    "exceptions",
]
