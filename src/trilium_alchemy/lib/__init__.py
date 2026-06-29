"""
Library which builds upon {obj}`BaseDeclarativeNote` to facilitate development of note
hierarchies and extensions encapsulated in a Python package.
"""

__submodules__ = ["extension_types", "note_types", "system_types"]

# <AUTOGEN_INIT>
from .extension_types import (
    BaseAppCssNote,
    BaseBackendScriptNote,
    BaseFrontendScriptNote,
    BaseTemplateNote,
    BaseThemeNote,
    BaseWidgetNote,
    BaseWorkspaceTemplateNote,
)
from .note_types import (
    CodeNote,
    CssNote,
    HtmlNote,
    JsBackendNote,
    JsFrontendNote,
    TextNote,
)
from .system_types import (
    BaseRootNote,
    BaseRootSystemNote,
    BaseSystemNote,
    BaseWorkspaceNote,
)

__all__ = [
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
    "note_types",
    "extension_types",
    "system_types",
]
