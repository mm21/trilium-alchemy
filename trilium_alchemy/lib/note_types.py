"""
Defines basic note types.
"""
from __future__ import annotations

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

    note_type_ = "code"
    icon = "bx bx-code"


class JsFrontendNote(CodeNote):
    """
    Defines a frontend script.
    """

    mime_ = "application/javascript;env=frontend"
    icon = "bx bxl-javascript"


class JsBackendNote(CodeNote):
    """
    Defines a backend script.
    """

    mime_ = "application/javascript;env=backend"
    icon = "bx bxl-javascript"


class CssNote(CodeNote):
    """
    Defines a CSS note.
    """

    mime_ = "text/css"
    icon = "bx bxs-file-css"


class HtmlNote(CodeNote):
    """
    Defines a HTML note.
    """

    mime_ = "text/html"
    icon = "bx bxs-file-html"


class TextNote(CodeNote):
    """
    Defines a text note.
    """

    mime_ = "text/plain"
    icon = "bx bx-text"
