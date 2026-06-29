"""
TriliumAlchemy: an SDK and CLI toolkit for Trilium Notes.
"""

__submodules__ = ["core", "lib"]
__canonical_children__ = __submodules__

# isort: off
# <AUTOGEN_INIT>
from .core import (
    Session,
    Note,
    Attachment,
    Branch,
    Label,
    Relation,
    BaseDeclarativeNote,
    BaseDeclarativeMixin,
    label,
    relation,
    label_def,
    relation_def,
    children,
    child,
    ReadOnlyError,
    ValidationError,
    State,
)
from .lib import (
    CodeNote,
    CssNote,
    HtmlNote,
    JsBackendNote,
    JsFrontendNote,
    TextNote,
    BaseTemplateNote,
    BaseWorkspaceTemplateNote,
    BaseAppCssNote,
    BaseThemeNote,
    BaseWidgetNote,
    BaseFrontendScriptNote,
    BaseBackendScriptNote,
    BaseWorkspaceNote,
    BaseSystemNote,
    BaseRootSystemNote,
    BaseRootNote,
)

__all__ = [
    "Session",
    "Note",
    "Attachment",
    "Branch",
    "Label",
    "Relation",
    "BaseDeclarativeNote",
    "BaseDeclarativeMixin",
    "label",
    "relation",
    "label_def",
    "relation_def",
    "children",
    "child",
    "ReadOnlyError",
    "ValidationError",
    "State",
    "CodeNote",
    "CssNote",
    "HtmlNote",
    "JsBackendNote",
    "JsFrontendNote",
    "TextNote",
    "BaseTemplateNote",
    "BaseWorkspaceTemplateNote",
    "BaseAppCssNote",
    "BaseThemeNote",
    "BaseWidgetNote",
    "BaseFrontendScriptNote",
    "BaseBackendScriptNote",
    "BaseWorkspaceNote",
    "BaseSystemNote",
    "BaseRootSystemNote",
    "BaseRootNote",
]
# </AUTOGEN_INIT>
