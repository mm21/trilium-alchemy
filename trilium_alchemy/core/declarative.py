"""
Decorators to add attributes and children declaratively.

```{todo}
Configuration of {obj}`Session` to ignore changes to 
{obj}`Branch.expanded` as this is mostly a UI concept. It can be clobbered
as children of {obj}`Note` subclasses force setting {obj}`Branch.expanded`.
```
"""

from __future__ import annotations

import os
from typing import Iterable, Literal, Any, cast
from functools import wraps, partial

from .note.note import Note, Mixin, BranchSpecT, patch_init
from .branch import Branch
from .attribute import Attribute, Label, Relation

__all__ = [
    "IconMixin",
    "label",
    "relation",
    "label_def",
    "relation_def",
    "children",
    "child",
]
__canonical_syms__ = __all__


def check_name(name: str, accumulate=False):
    """
    Check if attribute with this name already exists, and bail out if so
    and accumulate is False.
    """

    def _check_name(func):
        @wraps(func)
        def wrapper(
            self, attributes: list[Attribute], children: list[BranchSpecT]
        ):
            if accumulate is False and any(name == a.name for a in attributes):
                return
            return func(self, attributes, children)

        return wrapper

    return _check_name


class IconMixin(Mixin):
    """
    Enables setting the attribute {obj}`IconMixin.icon` to automatically add
    as value of `#iconClass` label.
    """

    icon: str | None = None
    """
    If provided, defines value of `#iconClass` label.
    """

    @check_name("iconClass")
    def init(self, attributes: list[Attribute], children: list[BranchSpecT]):
        """
        Set `#iconClass` value by defining {obj}`IconMixin.icon`.
        """
        if self.icon:
            attributes += [
                self.create_declarative_label("iconClass", self.icon)
            ]


def label(
    name: str,
    value: str = "",
    inheritable: bool = False,
    accumulate: bool = False,
):
    """
    Adds a {obj}`Label` to a {obj}`Note` or {obj}`Mixin` subclass.

    Example:

    ```
    @label("sorted")
    class MyNote(Note): pass
    ```

    :param name: Label name
    :param value: Label value, or empty string
    :param inheritable: Whether label should be inherited to children
    :param accumulate: Whether label should be added if an attribute with this name already exists from a subclassed {obj}`Note` or {obj}`Mixin`
    """

    @check_name(name, accumulate=accumulate)
    def init(self, attributes: list[Attribute], children: list[BranchSpecT]):
        attributes += [
            self.create_declarative_label(
                name, value=value, inheritable=inheritable
            )
        ]

    if value == "":
        label_doc = f"{name}"
    else:
        label_doc = f"{name}={value}"

    return patch_init(init, doc=f"- `#{label_doc}`")


def relation(
    name: str,
    target_cls: type[Note],
    inheritable: bool = False,
    accumulate: bool = False,
):
    """
    Adds a {obj}`Relation` to a {obj}`Note` or {obj}`Mixin` subclass.

    Example:

    ```
    # define a task template
    @label("task")
    class Task(Template):
        icon = "bx bx-task"

    # define a note with ~template=Task
    @relation("template", Task)
    class TaskNote(Note): pass

    # create a task
    task = TaskNote()

    assert task["template"] is Task()
    assert task["template"]["iconClass"] == "bx bx-task"
    ```
    :param name: Relation name
    :param target_cls: Class of relation target, will be instantiated when this note is instantiated (so it must have {obj}`Mixin.singleton`, {obj}`Mixin.note_id`, or {obj}`Mixin.note_id_seed` set)
    :param inheritable: Whether relation should be inherited to children
    :param accumulate: Whether relation should be added if an attribute with this name already exists from a subclassed {obj}`Note` or {obj}`Mixin`
    """

    @check_name(name, accumulate=accumulate)
    def init(self, attributes: list[Attribute], children: list[BranchSpecT]):
        assert (
            target_cls._is_singleton()
        ), f"Relation target {target_cls} must have a deterministic id by setting a note_id, note_id_seed, or singleton = True"

        # instantiate target first
        target: Note = target_cls(session=self._session)

        attribute_id = self._derive_id(Relation, name)
        attributes.append(
            Relation(
                name,
                target,
                inheritable=inheritable,
                session=self._session,
                attribute_id=attribute_id,
                owning_note=self,
            )
        )

    doc = f"`~{name}=`{{obj}}`{target_cls.__module__}.{target_cls.__name__}`"
    return patch_init(init, doc=f"- {doc}")


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
    Adds a {obj}`Label` definition (promoted label) to a {obj}`Note` or
    {obj}`Mixin` subclass.

    Example:

    ```
    @label("task")
    @label_def("priority", value_type="number")
    class Task(Template):
        icon = "bx bx-task"

    # buy cookies with high priority
    task = Note(title="Buy cookies", template=Task)
    task["priority"] = 10
    ```

    :param name: Label name
    :param promoted: Show in UI
    :param multi: Allow multiple labels with this name in UI
    :param value_type: Type of label value
    :param inheritable: Whether label should be inherited to children
    :param accumulate: Whether label should be added if an attribute with this name already exists from a subclassed {obj}`Note` or {obj}`Mixin`
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
    Adds a {obj}`Relation` definition (promoted relation) to a {obj}`Note` or
    {obj}`Mixin` subclass.

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
    :param accumulate: Whether relation should be added if an attribute with this name already exists from a subclassed {obj}`Note` or {obj}`Mixin`
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


def children(*children: type[Note] | tuple[type[Note], dict[str, Any]]):
    """
    Add {obj}`Note` subclasses as children, implicitly creating a {obj}`Branch`.

    Children may be provided as a class or tuple of `(cls, dict)`{l=python},
    with the `dict`{l=python} being used to set fields on the resulting branch.

    Example:

    ```
    class Child1(Note): pass
    class Child2(Note): pass

    # create Child1 with no Branch args, set prefix for Child2
    @children(Child1, (Child2, {"prefix": "My prefix"}))
    class Parent(Note): pass
    ```

    :param children: Tuple of `type[Note]`{l=python} or `(type[Note], dict)`{l=python}
    """

    def init(self, attributes: list[Attribute], children_: list[BranchSpecT]):
        children_ += list(cast(Iterable[BranchSpecT], children))

    return patch_init(init)


def child(child: type[Note], prefix: str = "", expanded: bool = False):
    """
    Instantiate provided class and add as child, implicitly creating
    a {obj}`Branch` and setting provided kwargs.

    Example:

    ```
    class Child(Note): pass

    @child(Child, prefix="My prefix")
    class Parent(Note): pass
    ```

    :param child: Subclass of {obj}`Note`
    :param prefix: Branch specific title prefix for child note
    :param expanded: `True`{l=python} if child note (as a folder) appears expanded in UI
    """

    def init(self, attributes: list[Attribute], children: list[BranchSpecT]):
        children.append(
            cast(
                BranchSpecT,
                (child, {"prefix": prefix, "expanded": expanded}),
            )
        )

    return patch_init(init)
