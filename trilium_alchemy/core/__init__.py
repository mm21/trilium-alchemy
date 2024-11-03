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

from . import attribute, branch, declarative, entity, exceptions, note, session
from .attribute import *  # noqa
from .branch import *  # noqa
from .declarative import *  # noqa
from .entity import *  # noqa
from .exceptions import *  # noqa
from .note import *  # noqa
from .session import *  # noqa

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
