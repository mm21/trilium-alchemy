"""
Library which builds upon {obj}`BaseDeclarativeNote` to facilitate development of note
hierarchies and extensions encapsulated in a Python package.
"""

__submodules__ = ["note_types", "extension_types", "system_types"]
__canonical_children__ = __submodules__

# isort: off
# <AUTOGEN_INIT>
from .note_types import (
    CodeNote,
    CssNote,
    HtmlNote,
    JsBackendNote,
    JsFrontendNote,
    TextNote,
)
from .extension_types import (
    BaseTemplateNote,
    BaseWorkspaceTemplateNote,
    BaseAppCssNote,
    BaseThemeNote,
    BaseWidgetNote,
    BaseFrontendScriptNote,
    BaseBackendScriptNote,
)
from .system_types import (
    BaseWorkspaceNote,
    BaseSystemNote,
    BaseRootSystemNote,
    BaseRootNote,
)

__all__ = [
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
