"""
Decorators to add attributes and children declaratively.
"""

from __future__ import annotations

from functools import wraps
from typing import Literal

from ..attribute import BaseAttribute
from ..branch.branch import Branch
from ..note.note import Note
from .base import BaseDeclarativeMixin, BaseDeclarativeNote

__all__ = [
    "label",
    "relation",
    "label_def",
    "relation_def",
    "children",
    "child",
]


def check_name(name: str, accumulate=False):
    """
    Check if attribute with this name already exists, and bail out if so
    and accumulate is False.
    """

    def _check_name(func):
        @wraps(func)
        def wrapper(
            self,
            attributes: list[BaseAttribute],
            children: list[Branch],
        ):
            if accumulate is False and any(name == a.name for a in attributes):
                return
            return func(self, attributes, children)

        return wrapper

    return _check_name


def label(
    name: str,
    value: str = "",
    inheritable: bool = False,
    accumulate: bool = False,
):
    """
    Adds a {obj}`Label` to a {obj}`BaseDeclarativeNote` or
    {obj}`BaseDeclarativeMixin` subclass.

    Example:

    ```
    @label("sorted")
    class MyNote(BaseDeclarativeNote): pass
    ```

    :param name: Label name
    :param value: Label value, or empty string
    :param inheritable: Whether label should be inherited to children
    :param accumulate: Whether label should be added if an attribute with this name already exists from a subclassed {obj}`BaseDeclarativeNote` or {obj}`BaseDeclarativeMixin`
    """

    @check_name(name, accumulate=accumulate)
    def init(
        self: BaseDeclarativeNote,
        attributes: list[BaseAttribute],
        _: list[Branch],
    ):
        attributes.append(
            self.create_declarative_label(
                name, value=value, inheritable=inheritable
            )
        )

    if value == "":
        label_doc = f"{name}"
    else:
        label_doc = f"{name}={value}"

    return _patch_init_decl(init, doc=f"- `#{label_doc}`")


def relation(
    name: str,
    target_cls: type[BaseDeclarativeNote],
    inheritable: bool = False,
    accumulate: bool = False,
):
    """
    Adds a {obj}`Relation` to a {obj}`BaseDeclarativeNote` or
    {obj}`BaseDeclarativeMixin` subclass.

    Example:

    ```
    # define a task template
    @label("task")
    class Task(BaseTemplateNote):
        icon = "bx bx-task"

    # define a note with ~template=Task
    @relation("template", Task)
    class TaskNote(BaseDeclarativeNote): pass

    # create a task
    task = TaskNote()

    assert task["template"] is Task()
    assert task["template"]["iconClass"] == "bx bx-task"
    ```
    :param name: Relation name
    :param target_cls: Class of relation target, will be instantiated when this note is instantiated (so it must have {obj}`BaseDeclarativeNote.singleton`, {obj}`BaseDeclarativeNote.note_id_`, or {obj}`BaseDeclarativeNote.note_id_seed` set)
    :param inheritable: Whether relation should be inherited to children
    :param accumulate: Whether relation should be added if an attribute with this name already exists from a subclassed {obj}`BaseDeclarativeNote` or {obj}`BaseDeclarativeMixin`
    """

    @check_name(name, accumulate=accumulate)
    def init(
        self: BaseDeclarativeMixin,
        attributes: list[BaseAttribute],
        _: list[Branch],
    ):
        assert (
            target_cls._is_singleton()
        ), f"Relation target {target_cls} must have a deterministic id by setting a note_id, note_id_seed, or singleton = True"

        # instantiate target first
        target: BaseDeclarativeNote = target_cls(session=self._session)

        attributes.append(
            self.create_declarative_relation(
                name, target, inheritable=inheritable
            )
        )

    doc = f"`~{name}=`{{obj}}`{target_cls.__module__}.{target_cls.__name__}`"
    return _patch_init_decl(init, doc=f"- {doc}")


def label_def(
    name: str,
    promoted: bool = True,
    multi: bool = False,
    value_type: Literal[
        "text", "number", "boolean", "date", "datetime", "url"
    ] = "text",
    inheritable: bool = False,
    accumulate: bool = False,
):
    """
    Adds a {obj}`Label` definition (promoted label) to a
    {obj}`BaseDeclarativeNote` or {obj}`BaseDeclarativeMixin` subclass.

    Example:

    ```
    @label("task")
    @label_def("priority", value_type="number")
    class Task(Template):
        icon = "bx bx-task"
    ```

    :param name: Label name
    :param promoted: Show in UI
    :param multi: Allow multiple labels with this name in UI
    :param value_type: Type of label value
    :param inheritable: Whether label should be inherited to children
    :param accumulate: Whether label should be added if an attribute with this name already exists from a subclassed {obj}`BaseDeclarativeNote` or {obj}`BaseDeclarativeMixin`
    """

    name = f"label:{name}"

    params = []

    if promoted:
        params.append("promoted")

    if multi:
        params.append("multi")
    else:
        params.append("single")

    params.append(value_type)

    value = ",".join(params)
    return label(name, value, inheritable=inheritable, accumulate=accumulate)


def relation_def(
    name: str,
    promoted: bool = True,
    multi: bool = False,
    inverse: str | None = None,
    inheritable: bool = False,
    accumulate: bool = False,
):
    """
    Adds a {obj}`Relation` definition (promoted relation) to a
    {obj}`BaseDeclarativeNote` or {obj}`BaseDeclarativeMixin` subclass.

    Example:

    ```
    @label("task")
    @label_def("priority", value_type="number")
    @relation_def("project", inheritable=True)
    class Task(Template):
        icon = "bx bx-task"
    ```

    :param name: Relation name
    :param promoted: Show in UI
    :param multi: Allow multiple relations with this name in UI
    :param inverse: Inverse relation, e.g. if `name = "isParentOf"`{l=python} this could be `"isChildOf"`{l=python}
    :param inheritable: Whether relation should be inherited to children
    :param accumulate: Whether relation should be added if an attribute with this name already exists from a subclassed {obj}`BaseDeclarativeNote` or {obj}`BaseDeclarativeMixin`
    """

    name = f"relation:{name}"

    params = []

    if promoted:
        params.append("promoted")

    if multi:
        params.append("multi")
    else:
        params.append("single")

    if inverse is not None:
        params.append(f"inverse={inverse}")

    value = ",".join(params)
    return label(name, value, inheritable=inheritable, accumulate=accumulate)


def children(
    *children: type[BaseDeclarativeNote] | tuple[type[BaseDeclarativeNote], str]
):
    """
    Add {obj}`BaseDeclarativeNote` subclasses as children, implicitly
    creating a {obj}`Branch`. May use a tuple of `(child_cls, prefix)` to
    additionally set branch prefix.

    Example:

    ```
    class Child1(BaseDeclarativeNote):
        pass

    class Child2(BaseDeclarativeNote):
        pass

    @children(
        Child1,
        (Child2, "My prefix"),
    )
    class Parent(BaseDeclarativeNote):
        pass
    ```

    :param children: Classes to add as children
    """

    def init(
        self: BaseDeclarativeNote,
        _: list[BaseAttribute],
        children_: list[Branch],
    ):
        for child in children:
            child_cls: type[BaseDeclarativeNote]
            prefix: str

            if isinstance(child, tuple):
                child_cls, prefix = child
            else:
                child_cls, prefix = child, ""

            assert issubclass(
                child_cls, BaseDeclarativeNote
            ), f"Unexpected child type, must subclass BaseDeclarativeNote: {type(child_cls)}, {child_cls}"
            children_.append(
                self.create_declarative_child(child_cls, prefix=prefix)
            )

    return _patch_init_decl(init)


def child(child: type[Note], prefix: str = "", expanded: bool | None = None):
    """
    Instantiate provided class and add as child, creating a
    {obj}`Branch` and setting provided kwargs.

    Example:

    ```
    class Child(BaseDeclarativeNote):
        pass

    @child(Child, prefix="My prefix")
    class Parent(BaseDeclarativeNote):
        pass
    ```

    :param child: Subclass of {obj}`Note`
    :param prefix: Branch specific title prefix for child note
    :param expanded: `True`{l=python} if child note (as a folder) appears expanded in UI; `None{l=python}` to preserve existing value
    """

    def init(
        self: BaseDeclarativeNote,
        _: list[BaseAttribute],
        children: list[Branch],
    ):
        children.append(
            self.create_declarative_child(
                child, prefix=prefix, expanded=expanded
            )
        )

    return _patch_init_decl(init)


def _patch_init_decl(init, doc: str | None = None):
    """
    Insert provided init function in class's declarative init sequence.
    """

    def init_decl_new[
        MixinT: BaseDeclarativeMixin
    ](cls: type[MixinT]) -> type[MixinT]:
        assert issubclass(cls, BaseDeclarativeMixin)
        init_decl_old = cls._init_decl

        @wraps(init_decl_old)
        def _init_decl(
            self,
            cls_decl,
            attributes: list[BaseAttribute],
            children: list[Branch],
        ):
            if cls is cls_decl:
                # invoke init patch
                init(self, attributes, children)

                # invoke old init
                init_decl_old(self, cls_decl, attributes, children)

        cls._init_decl = _init_decl

        if doc:
            # append to docstring
            cls._decorator_doc.append(doc)

        return cls

    return init_decl_new
