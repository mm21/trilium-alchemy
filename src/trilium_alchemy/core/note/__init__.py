__submodules__ = ["note", "attachments"]

# <AUTOGEN_INIT>
from .attachments import (
    Attachment,
    Attachments,
)
from .note import (
    Note,
)

__all__ = ["Note", "Attachment", "Attachments"]
# </AUTOGEN_INIT>

__canonical_syms__ = __all__  # type: ignore[name-defined]
__canonical_children__ = [
    "attributes",
    "branches",
    "content",
    "attachments",
]
