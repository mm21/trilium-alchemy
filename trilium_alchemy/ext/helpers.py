"""
Defines more specific classes to assist in the development of extensions.

A common note structure is to create "system" notes which hold templates,
scripts, etc. This module provides automation of such a system, with a 
{obj}`BaseSystem` class to hold various types of notes.

The root system {obj}`BaseRootSystem` additionally holds themes and a
built-in stylesheet which hides the "Create child note" button in the UI
for subclass-managed notes ({obj}`Mixin.leaf` is `False`{l=python}).

If a note hierarchy is defined under a {obj}`BaseRoot` subclass,
a {obj}`BaseRootSystem` is automatically added.

For a complete example of a note hierarchy using these classes, see 
`trilium-alchemy/example/event-tracker` and its documentation at
{ref}`event-tracker`.

A brief example is shown here:

```
# define a widget
class MyWidget(Widget): 
    content_file = "assets/myWidget.js"

# define a system note
class System(BaseRootSystem):
    widgets = [MyWidget]

# define a root note
# use @children or @child to add child notes
class MyRoot(BaseRoot):
    system = System
```
"""
from __future__ import annotations
import os
from typing import Type, Any
from ..core import (
    Note,
    Mixin,
    Branch,
    Attribute,
    label,
)
from .types import (
    CssNote,
    JsFrontendNote,
    JsBackendNote,
)

__all__ = [
    "Template",
    "WorkspaceTemplate",
    "Workspace",
    "AppCss",
    "Theme",
    "Widget",
    "FrontendScript",
    "BackendScript",
    "BaseSystem",
    "BaseRootSystem",
    "BaseRoot",
]


# TODO: should this be published? enable icon = "..." capability for any Note
# subclass
class IconMixin(Mixin):
    icon: str = None
    """
    If provided, defines value of `#iconClass` label.
    """

    def init(self, attributes: list[Attribute], children: list[Branch]):
        """
        Set `#iconClass` value by defining {obj}`IconMixin.icon`.
        """
        if self.icon:
            attributes += [
                self.create_declarative_label("iconClass", self.icon)
            ]


class BaseTemplate(Note, IconMixin):
    singleton = True
    """
    Templates should have exactly one instance, allowing
    them to be targets of declarative relations
    """

    _force_leaf = True

    @classmethod
    def instance(cls, *args, **kwargs):
        """
        Create new note with `~template` relation to this note, passing through
        constructor args.

        Example:

        ```
        # define a task template (not shown: instantiation in hierarchy)
        @label_def("priority", value_type="number")
        class Task(Template): # or WorkspaceTemplate
            icon = "bx bx-task"

        # create a new note with ~template=Task
        task = Task.instance(title="Buy cookies")

        # equivalent to:
        task = Note(title="Buy cookies", template=Task)
        ```
        """
        return Note(*args, **kwargs, template=cls)


@label("template")
class Template(BaseTemplate):
    """
    Defines a template.
    """


@label("workspaceTemplate")
class WorkspaceTemplate(BaseTemplate):
    """
    Defines a workspace template.
    """


@label("workspace")
class Workspace(Note, IconMixin):
    """
    Defines a workspace.

    - Adds system note, if {obj}`Workspace.system` set
    """

    singleton = True

    system: BaseSystem = None

    def init(self, attributes: list[Attribute], children: list[Branch]):
        # add system note, if provided
        if self.system:
            children.append(self.create_declarative_child(self.system))


@label("appCss")
class AppCss(CssNote):
    """
    Defines a CSS note with label `#appCss`.

    Use {obj}`Note.content_file` to set content from file.
    """

    singleton = True


class Theme(CssNote):
    """
    Defines a theme.

    Use {obj}`Note.content_file` to set content from file.

    Adds label: `#appTheme=`{obj}`Theme.theme_name`
    - If `None`{l=python}, defaults to class name
    """

    singleton = True

    theme_name: str = None
    """
    Name of theme, or `None`{l=python} to use class name
    """

    def init(self, attributes: list[Attribute], children: list[Branch]):
        # default to class name if name not provided
        if self.theme_name is None:
            self.theme_name = type(self).__name__

        attributes += [
            self.create_declarative_label("appTheme", self.theme_name)
        ]


@label("widget")
class Widget(JsFrontendNote):
    """
    Defines a widget.
    """

    singleton = True


class ScriptMixin(Mixin):
    """
    Mixin which sets note title from script's filename. This allows
    reuse of functions by adding them as children of other scripts.
    """

    def init(self, attributes, children):
        return {"title": os.path.basename(self.content_file).split(".")[0]}


class FrontendScript(JsFrontendNote, ScriptMixin):
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


# TODO: add validation of known event relation
# w/warning for unknown events?
class BackendScript(JsBackendNote, ScriptMixin):
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


class Function(FrontendScript):
    pass


# categories which hold user-visible notes
@label("archived")
class Category(Note):
    pass


# categories which hold archived notes
@label("archived", inheritable=True)
class HiddenCategory(Note):
    pass


# categories under System note
class Templates(Category):
    pass


class WorkspaceTemplates(Category):
    pass


class Stylesheets(HiddenCategory):
    pass


class Widgets(HiddenCategory):
    pass


class Scripts(HiddenCategory):
    pass


# TODO: long term: automatically create System and populate by
# checking bases of classes in module?
@label("iconClass", "bx bx-bracket")
@label("archived")
class BaseSystem(Note):
    """
    Base class for a "system" note, a collection of various types of
    infrastructure notes.
    """

    templates: list[Type[Template]] = None
    """
    List of {obj}`Template` subclasses.
    """

    workspace_templates: list[Type[WorkspaceTemplate]] = None
    """
    List of {obj}`WorkspaceTemplate` subclasses.
    """

    stylesheets: list[Type[AppCss]] = None
    """
    List of {obj}`AppCss` subclasses.
    """

    widgets: list[Type[Widget]] = None
    """
    List of {obj}`Widget` subclasses.
    """

    scripts: list[Type[FrontendScript | BackendScript]] = None
    """
    List of {obj}`FrontendScript` or {obj}`BackendScript` subclasses.
    """

    def init(self, attributes: list[Attribute], children: list[Branch]):
        if self.templates:
            children.append(
                self.create_declarative_child(
                    Templates, children=self.templates
                )
            )

        if self.workspace_templates:
            children.append(
                self.create_declarative_child(
                    WorkspaceTemplates, children=self.workspace_templates
                )
            )

        if self.stylesheets:
            children.append(
                self.create_declarative_child(
                    Stylesheets, children=self.stylesheets
                )
            )

        if self.widgets:
            children.append(
                self.create_declarative_child(Widgets, children=self.widgets)
            )

        if self.scripts:
            children.append(
                self.create_declarative_child(Scripts, children=self.scripts)
            )


# themes are global, so only maintain in root System note
class Themes(Category):
    pass


class TriliumAlchemyStylesheet(AppCss):
    """
    Custom stylesheet to hide "Create child note" button for
    non-leaf notes. This is to reflect the fact that these
    notes are managed by code rather than in the UI.
    """

    content_file = "assets/system.css"


class TriliumAlchemySystem(BaseSystem):
    """
    Built-in `System` note to insert custom stylesheet.
    """

    stylesheets = [TriliumAlchemyStylesheet]


class BaseRootSystem(BaseSystem):
    """
    Base class for a root "system" note, additionally containing themes
    and adding a built-in {obj}`BaseSystem` subclass.
    """

    themes: list[Type[Theme]] = None
    """
    List of {obj}`Theme` subclasses
    """

    def init(self, attributes: list[Attribute], children: list[Branch]):
        if self.themes:
            children.append(
                self.create_declarative_child(Themes, children=self.themes)
            )

        # add built-in system note
        children.append(self.create_declarative_child(TriliumAlchemySystem))


class BaseRoot(Note):
    """
    Base class for a hierarchy root note.
    """

    title = "root"
    system: Type[BaseRootSystem] = BaseRootSystem

    def init(self, attributes: list[Attribute], children: list[Branch]):
        if self.system:
            children.append(self.create_declarative_child(self.system))
