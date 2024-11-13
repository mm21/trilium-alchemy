"""
Defines more specific classes to assist in the development of extensions.

A common note structure is to create "system" notes which hold templates,
scripts, etc. This module provides automation of such a system, with a 
{obj}`BaseSystem` class to hold various types of notes.

The root system {obj}`BaseRootSystemNote` additionally holds themes and a
built-in stylesheet which hides the "Create child note" button in the UI
for subclass-managed notes 
({obj}`BaseDeclarativeNote.leaf` is `False`{l=python}).

If a note hierarchy is defined under a {obj}`BaseRootNote` subclass,
a {obj}`BaseRootSystemNote` is automatically added.

For a complete example of a note hierarchy using these classes, see 
`trilium-alchemy/example/event-tracker` and its documentation at
{ref}`event-tracker`.

A brief example is shown here:

```
# define a widget
class MyWidget(Widget): 
    content_file = "assets/myWidget.js"

# define a system note
class System(BaseRootSystemNote):
    widgets = [MyWidget]

# define a root note
# use @children or @child to add child notes
class MyRoot(BaseRootNote):
    system = System
```
"""
from __future__ import annotations

from typing import Type, cast

from ..core import BaseAttribute, Note, label
from ..core.declarative.base import BaseDeclarativeNote, is_inherited
from ..core.note.note import BranchSpecT
from .types import CssNote, JsBackendNote, JsFrontendNote

__all__ = [
    "BaseTemplateNote",
    "BaseWorkspaceTemplateNote",
    "BaseWorkspaceNote",
    "BaseAppCssNote",
    "BaseThemeNote",
    "BaseWidgetNote",
    "BaseFrontendScriptNote",
    "BaseBackendScriptNote",
    "BaseSystemNote",
    "BaseWorkspaceRootNote",
    "BaseRootSystemNote",
    "BaseRootNote",
]


class _BaseTemplateNote(BaseDeclarativeNote):
    # note_id generated from class name
    idempotent = True

    _force_leaf = True

    @classmethod
    def instance(cls, *args, **kwargs):
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


@label("workspace")
class BaseWorkspaceNote(BaseDeclarativeNote):
    """
    Defines a workspace.

    - Adds system note, if {obj}`Workspace.system` set
    """

    singleton = True
    system: BaseSystemNote = None

    def init(self, _, children: list[BranchSpecT]):
        # add system note, if provided
        if self.system:
            children.append(self.create_declarative_child(self.system))


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

    Adds label: `#appTheme=`{obj}`Theme.theme_name`
    - If `None`{l=python}, defaults to class name
    """

    singleton = True

    theme_name: str = None
    """
    Name of theme, or `None`{l=python} to use class name
    """

    def init(self, attributes: list[BaseAttribute], _):
        # default to class name if name not provided
        if self.theme_name is None:
            self.theme_name = type(self).__name__

        attributes.append(
            self.create_declarative_label("appTheme", self.theme_name)
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


# TODO: add validation of known event relation
# w/warning for unknown events?
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


# categories which hold user-visible notes
@label("archived")
class BaseCategoryNote(BaseDeclarativeNote):
    pass


# categories which hold archived notes
@label("archived", inheritable=True)
class BaseHiddenCategoryNote(BaseDeclarativeNote):
    pass


# categories under System note


class Templates(BaseCategoryNote):
    pass


class WorkspaceTemplates(BaseCategoryNote):
    pass


class Stylesheets(BaseHiddenCategoryNote):
    pass


class Widgets(BaseHiddenCategoryNote):
    pass


class Scripts(BaseHiddenCategoryNote):
    pass


# TODO: long term: automatically create System and populate by
# checking bases of classes in module?
# - e.g. add all notes inheriting from BaseTemplateNote to "Templates" note
@label("iconClass", "bx bx-bracket")
@label("archived")
class BaseSystemNote(BaseDeclarativeNote):
    """
    Base class for a "system" note, a collection of various types of
    infrastructure notes.

    Attributes such as {obj}`BaseSystem.templates` from any base classes
    are appended.
    """

    templates: list[Type[BaseTemplateNote]] | None = None
    """
    List of {obj}`Template` subclasses.
    """

    workspace_templates: list[Type[BaseWorkspaceTemplateNote]] | None = None
    """
    List of {obj}`BaseWorkspaceTemplateNote` subclasses.
    """

    stylesheets: list[Type[BaseAppCssNote]] | None = None
    """
    List of {obj}`AppCss` subclasses.
    """

    widgets: list[Type[BaseWidgetNote]] | None = None
    """
    List of {obj}`Widget` subclasses.
    """

    scripts: list[
        Type[BaseFrontendScriptNote | BaseBackendScriptNote]
    ] | None = None
    """
    List of {obj}`FrontendScript` or {obj}`BackendScript` subclasses.
    """

    def init(self, _: list[BaseAttribute], children: list[BranchSpecT]):
        children.append(
            self.create_declarative_child(
                Templates, children=self._collect_notes("templates")
            )
        )
        children.append(
            self.create_declarative_child(
                WorkspaceTemplates,
                children=self._collect_notes("workspace_templates"),
            )
        )
        children.append(
            self.create_declarative_child(
                Stylesheets, children=self._collect_notes("stylesheets")
            )
        )
        children.append(
            self.create_declarative_child(
                Widgets, children=self._collect_notes("widgets")
            )
        )
        children.append(
            self.create_declarative_child(
                Scripts, children=self._collect_notes("scripts")
            )
        )

    def _collect_notes(self, attr: str) -> list[Note]:
        """
        Get the attribute with the given name, appending those of
        base classes.
        """

        notes: list[Note] = []

        for cls in type(self).mro():
            if issubclass(cls, BaseSystemNote):
                # skip if it doesn't have this attribute
                if not hasattr(cls, attr):
                    continue

                # skip if the attribute belongs to a subclass
                if is_inherited(cls, attr):
                    continue

                attr_list = cast(list[Note] | None, getattr(cls, attr))

                if attr_list is not None:
                    # validate
                    assert isinstance(attr_list, list)
                    for note_cls in attr_list:
                        assert issubclass(
                            note_cls, BaseDeclarativeNote
                        ), f"Got unexpected class in note attribute '{attr}': {note_cls} {type(note_cls)}"

                        notes.append(note_cls(session=self.session))

                    # notes += attr_list

        return notes


@label("workspace")
class BaseWorkspaceRootNote(BaseDeclarativeNote):
    """
    Base class for a workspace root.

    - Adds `#workspace` label
    - Adds {obj}`BaseSystem` child note, if attribute `system` is set
    """

    system: type[BaseSystemNote] | None = None

    def init(self, _: list[BaseAttribute], children: list[BranchSpecT]):
        if self.system is not None:
            children.append(self.create_declarative_child(self.system))


# themes are global, so only maintain in root System note
class ThemesNote(BaseCategoryNote):
    pass


class TriliumAlchemyStylesheetNote(BaseAppCssNote):
    """
    Custom stylesheet to hide "Create child note" button for
    non-leaf notes. This is to reflect the fact that these
    notes are managed by code rather than in the UI.
    """

    content_file = "assets/system.css"


class TriliumAlchemySystemNote(BaseSystemNote):
    """
    Built-in `System` note to insert custom stylesheet.
    """

    stylesheets = [TriliumAlchemyStylesheetNote]


class BaseRootSystemNote(BaseSystemNote):
    """
    Base class for a root "system" note, additionally containing themes.
    """

    themes: list[Type[BaseThemeNote]] | None = None
    """
    List of {obj}`Theme` subclasses
    """

    def init(self, _: list[BaseAttribute], children: list[BranchSpecT]):
        # add built-in system note
        children.append(self.create_declarative_child(TriliumAlchemySystemNote))

        # add themes
        children.append(
            self.create_declarative_child(
                ThemesNote, children=self._collect_notes("themes")
            )
        )


class BaseRootNote(BaseDeclarativeNote):
    """
    Base class for a hierarchy root note.
    """

    title_ = "root"
    system: Type[BaseRootSystemNote] | None = BaseRootSystemNote

    def init(self, _: list[BaseAttribute], children: list[BranchSpecT]):
        if self.system is not None:
            children.append(self.create_declarative_child(self.system))
