"""
Defines basic note types used in extensions.
"""

from ..core import Note

__all__ = [
    "CodeNote",
    "JsFrontendNote",
    "JsBackendNote",
    "CssNote",
]


class CodeNote(Note):
    """
    Defines a `code` note.
    """

    note_type = "code"


class JsFrontendNote(CodeNote):
    """
    Defines a frontend script.
    """

    mime = "application/javascript;env=frontend"


class JsBackendNote(CodeNote):
    """
    Defines a backend script.
    """

    mime = "application/javascript;env=backend"


class CssNote(CodeNote):
    """
    Defines a CSS note.
    """

    mime = "text/css"
