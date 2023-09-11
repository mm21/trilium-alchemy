"""
Defines basic note types used in extensions.
"""

from ..core import Note, IconMixin

__all__ = [
    "CodeNote",
    "CssNote",
    "HtmlNote",
    "JsBackendNote",
    "JsFrontendNote",
    "TextNote",
]


class CodeNote(Note, IconMixin):
    """
    Defines a `code` note.
    """

    note_type = "code"
    icon = "bx bx-code"


class JsFrontendNote(CodeNote):
    """
    Defines a frontend script.
    """

    mime = "application/javascript;env=frontend"
    icon = "bx bxl-javascript"


class JsBackendNote(CodeNote):
    """
    Defines a backend script.
    """

    mime = "application/javascript;env=backend"
    icon = "bx bxl-javascript"


class CssNote(CodeNote):
    """
    Defines a CSS note.
    """

    mime = "text/css"
    icon = "bx bxs-file-css"


class HtmlNote(CodeNote):
    """
    Defines a HTML note.
    """

    mime = "text/html"
    icon = "bx bxs-file-html"


class TextNote(CodeNote):
    """
    Defines a text note.
    """

    mime = "text/plain"
    icon = "bx bx-text"
