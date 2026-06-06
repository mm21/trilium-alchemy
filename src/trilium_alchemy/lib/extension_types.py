"""
Defines more specific classes to assist in the development of extensions.
"""
from __future__ import annotations

from ..core import BaseAttribute, Branch, Note, label
from ..core.declarative.base import BaseDeclarativeNote
from .note_types import CssNote, JsBackendNote, JsFrontendNote

__all__ = [
    "BaseTemplateNote",
    "BaseWorkspaceTemplateNote",
    "BaseAppCssNote",
    "BaseThemeNote",
    "BaseWidgetNote",
    "BaseFrontendScriptNote",
    "BaseBackendScriptNote",
]


class _BaseTemplateNote(BaseDeclarativeNote):
    idempotent = True
    _force_leaf = True

    @classmethod
    def new_instance(cls, *args, **kwargs):
        """
        Create new note with `~template` relation to this note, passing through
        constructor args.
        """
        return Note(*args, **kwargs, template=cls)


@label("template")
class BaseTemplateNote(_BaseTemplateNote):
    """
    Defines a template.
    """


@label("workspaceTemplate")
class BaseWorkspaceTemplateNote(_BaseTemplateNote):
    """
    Defines a workspace template.
    """


@label("appCss")
class BaseAppCssNote(CssNote):
    """
    Defines a CSS note with label `#appCss`.

    Use {obj}`BaseDeclarativeNote.content_file` to set content from file.
    """

    singleton = True


class BaseThemeNote(CssNote):
    """
    Defines a theme.

    Use {obj}`BaseDeclarativeNote.content_file` to set content from file.

    Adds label: `#appTheme=`{obj}`BaseThemeNote.theme_name`
    - If `None`{l=python}, defaults to class name
    """

    singleton = True

    theme_name: str | None = None
    """
    Name of theme, or `None`{l=python} to use class name.
    """

    def init(self, attributes: list[BaseAttribute], _: list[Branch]):
        # default to class name if name not provided
        attributes.append(
            self.create_declarative_label(
                "appTheme", self.theme_name or type(self).__name__
            )
        )


@label("widget")
class BaseWidgetNote(JsFrontendNote):
    """
    Defines a widget.
    """

    singleton = True


class BaseFrontendScriptNote(JsFrontendNote):
    """
    Defines a frontend script.

    Example:

    ```
    class MyFunction(FrontendScript):
        content_file = 'assets/myFunction.js'

    @children(MyFunction)
    class MyWidget(Widget): pass
    ```
    """

    singleton = True
    _stem_title = True


class BaseBackendScriptNote(JsBackendNote):
    """
    Defines a backend script.

    Example:

    ```
    class UpdateSomeOtherAttribute(BackendScript):
        content_file = 'assets/updateSomeOtherAttribute.js'

    @relation('runOnAttributeCreation', UpdateSomeOtherAttribute)
    @relation('runOnAttributeChange', UpdateSomeOtherAttribute)
    class MyTemplate(Template): pass
    ```
    """

    singleton = True
    _stem_title = True
