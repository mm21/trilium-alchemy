"""
A common note structure is to create "system" notes which hold templates,
scripts, etc. This module facilitates maintenance of such a system, with a 
{obj}`BaseSystemNote` class to hold such notes.

The root system {obj}`BaseRootSystemNote` additionally holds themes and a
built-in stylesheet which hides the "Create child note" button in the UI
for subclass-managed notes 
({obj}`BaseDeclarativeNote.leaf` is `False`{l=python}).

If a note hierarchy is defined under a {obj}`BaseRootNote` subclass,
a {obj}`BaseRootSystemNote` is automatically added.

For a complete example of a note hierarchy using these classes, see 
`trilium-alchemy/examples/event-tracker` and its documentation at
{ref}`event-tracker`.
"""
from __future__ import annotations

from typing import cast

from ..core import BaseAttribute, Branch, Note, label
from ..core.declarative.base import BaseDeclarativeNote, is_inherited
from .extension_types import (
    BaseAppCssNote,
    BaseBackendScriptNote,
    BaseFrontendScriptNote,
    BaseTemplateNote,
    BaseThemeNote,
    BaseWidgetNote,
    BaseWorkspaceTemplateNote,
)

__all__ = [
    "BaseWorkspaceNote",
    "BaseSystemNote",
    "BaseRootSystemNote",
    "BaseRootNote",
]


@label("workspace")
class BaseWorkspaceNote(BaseDeclarativeNote):
    """
    Defines a workspace root.

    - Adds `#workspace` label
    - Adds {obj}`BaseSystemNote` child note, if attribute `system` is set
    """

    singleton = True
    system: type[BaseSystemNote] | None = None

    def init(self, _: list[BaseAttribute], children: list[Branch]):
        if self.system is not None:
            children.append(self.create_declarative_child(self.system))


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


class Themes(BaseCategoryNote):
    pass


class Stylesheets(BaseHiddenCategoryNote):
    pass


class Widgets(BaseHiddenCategoryNote):
    pass


class Scripts(BaseHiddenCategoryNote):
    pass


# TODO: long term: automatically create System and populate by
# checking bases of classes in module
# - e.g. add all notes inheriting from BaseTemplateNote to "Templates" note
@label("iconClass", "bx bx-bracket")
@label("archived")
class BaseSystemNote(BaseDeclarativeNote):
    """
    Base class for a "system" note, a collection of various types of
    infrastructure notes.

    Attributes such as {obj}`BaseSystemNote.templates` from any base classes
    are appended.
    """

    templates: list[type[BaseTemplateNote]] | None = None
    """
    List of {obj}`Template` subclasses.
    """

    workspace_templates: list[type[BaseWorkspaceTemplateNote]] | None = None
    """
    List of {obj}`BaseWorkspaceTemplateNote` subclasses.
    """

    stylesheets: list[type[BaseAppCssNote]] | None = None
    """
    List of {obj}`AppCss` subclasses.
    """

    widgets: list[type[BaseWidgetNote]] | None = None
    """
    List of {obj}`Widget` subclasses.
    """

    scripts: list[
        type[BaseFrontendScriptNote | BaseBackendScriptNote]
    ] | None = None
    """
    List of {obj}`FrontendScript` or {obj}`BackendScript` subclasses.
    """

    def init(self, _: list[BaseAttribute], children: list[Branch]):
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

    themes: list[type[BaseThemeNote]] | None = None
    """
    List of {obj}`Theme` subclasses
    """

    def init(self, _: list[BaseAttribute], children: list[Branch]):
        # add built-in system note
        children.append(self.create_declarative_child(TriliumAlchemySystemNote))

        # add themes
        children.append(
            self.create_declarative_child(
                Themes, children=self._collect_notes("themes")
            )
        )


class BaseRootNote(BaseDeclarativeNote):
    """
    Base class for a hierarchy root note.
    """

    title_ = "root"
    system: type[BaseRootSystemNote] | None = BaseRootSystemNote

    def init(self, _: list[BaseAttribute], children: list[Branch]):
        if self.system is not None:
            children.append(self.create_declarative_child(self.system))
