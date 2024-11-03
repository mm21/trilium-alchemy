"""
Defines basic note types used in extensions.
"""

from ..core.declarative import BaseDeclarativeNote

__all__ = [
    "CodeNote",
    "CssNote",
    "HtmlNote",
    "JsBackendNote",
    "JsFrontendNote",
    "TextNote",
]


class CodeNote(BaseDeclarativeNote):
    """
    Defines a `code` note.
    """

    decl_note_type = "code"
    icon = "bx bx-code"


class JsFrontendNote(CodeNote):
    """
    Defines a frontend script.
    """

    decl_mime = "application/javascript;env=frontend"
    icon = "bx bxl-javascript"


class JsBackendNote(CodeNote):
    """
    Defines a backend script.
    """

    decl_mime = "application/javascript;env=backend"
    icon = "bx bxl-javascript"


class CssNote(CodeNote):
    """
    Defines a CSS note.
    """

    decl_mime = "text/css"
    icon = "bx bxs-file-css"


class HtmlNote(CodeNote):
    """
    Defines a HTML note.
    """

    decl_mime = "text/html"
    icon = "bx bxs-file-html"


class TextNote(CodeNote):
    """
    Defines a text note.
    """

    decl_mime = "text/plain"
    icon = "bx bx-text"
