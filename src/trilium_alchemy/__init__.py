"""
TriliumAlchemy: an SDK and CLI toolkit for Trilium Notes.
"""

__submodules__ = ["core", "lib"]

# <AUTOGEN_INIT>
from .core import (
    Attachment,
    Attachments,
    BaseAttribute,
    BaseDeclarativeMixin,
    BaseDeclarativeNote,
    BaseEntity,
    Branch,
    Label,
    Note,
    ReadOnlyError,
    Relation,
    Session,
    State,
    ValidationError,
    child,
    children,
    label,
    label_def,
    relation,
    relation_def,
)
from .lib import (
    BaseAppCssNote,
    BaseBackendScriptNote,
    BaseFrontendScriptNote,
    BaseRootNote,
    BaseRootSystemNote,
    BaseSystemNote,
    BaseTemplateNote,
    BaseThemeNote,
    BaseWidgetNote,
    BaseWorkspaceNote,
    BaseWorkspaceTemplateNote,
    CodeNote,
    CssNote,
    HtmlNote,
    JsBackendNote,
    JsFrontendNote,
    TextNote,
)

__all__ = [
    "Session",
    "Note",
    "Attachment",
    "Attachments",
    "Branch",
    "BaseAttribute",
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
    "BaseEntity",
    "State",
    "BaseTemplateNote",
    "BaseWorkspaceTemplateNote",
    "BaseAppCssNote",
    "BaseThemeNote",
    "BaseWidgetNote",
    "BaseFrontendScriptNote",
    "BaseBackendScriptNote",
    "CodeNote",
    "CssNote",
    "HtmlNote",
    "JsBackendNote",
    "JsFrontendNote",
    "TextNote",
    "BaseWorkspaceNote",
    "BaseSystemNote",
    "BaseRootSystemNote",
    "BaseRootNote",
]
# </AUTOGEN_INIT>

__canonical_children__ = [
    "core",
    "lib",
]
