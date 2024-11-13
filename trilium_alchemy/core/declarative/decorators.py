"""
Decorators to add attributes and children declaratively.

```{todo}
Configuration of `Session` to ignore changes to 
`Branch.expanded` as this is mostly a UI concept. It can be clobbered
as children of `BaseDeclarativeNote` subclasses force setting 
`Branch.expanded`.
```
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Iterable, Literal, cast

from ..attribute import BaseAttribute
from ..note.note import BranchSpecT, Note
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
            self, attributes: list[BaseAttribute], children: list[BranchSpecT]
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
    Adds a {obj}`Label` to a {obj}`Note` or {obj}`BaseDeclarativeMixin` subclass.

    Example:

    ```
    @label("sorted")
    class MyNote(Note): pass
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
        children: list[BranchSpecT],
    ):
        assert isinstance(self, BaseDeclarativeNote)

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
    target_cls: type[Note],
    inheritable: bool = False,
    accumulate: bool = False,
):
    """
    Adds a {obj}`Relation` to a {obj}`Note` or {obj}`BaseDeclarativeMixin` subclass.

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
    :param target_cls: Class of relation target, will be instantiated when this note is instantiated (so it must have {obj}`BaseDeclarativeNote.singleton`, {obj}`BaseDeclarativeNote.note_id_`, or {obj}`BaseDeclarativeNote.note_id_seed` set)
    :param inheritable: Whether relation should be inherited to children
    :param accumulate: Whether relation should be added if an attribute with this name already exists from a subclassed {obj}`BaseDeclarativeNote` or {obj}`BaseDeclarativeMixin`
    """

    @check_name(name, accumulate=accumulate)
    def init(
        self: BaseDeclarativeMixin,
        attributes: list[BaseAttribute],
        children: list[BranchSpecT],
    ):
        assert isinstance(self, BaseDeclarativeNote)
        assert (
            target_cls._is_singleton()
        ), f"Relation target {target_cls} must have a deterministic id by setting a note_id, note_id_seed, or singleton = True"

        # instantiate target first
        target: Note = target_cls(session=self._session)

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
    Adds a {obj}`Label` definition (promoted label) to a {obj}`Note` or
    {obj}`BaseDeclarativeMixin` subclass.

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
    Adds a {obj}`Relation` definition (promoted relation) to a {obj}`Note` or
    {obj}`BaseDeclarativeMixin` subclass.

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

    def init(
        self: BaseDeclarativeNote,
        attributes: list[BaseAttribute],
        children_: list[BranchSpecT],
    ):
        assert isinstance(self, BaseDeclarativeNote)

        children_ += list(cast(Iterable[BranchSpecT], children))

    return _patch_init_decl(init)


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

    def init(
        self: BaseDeclarativeNote,
        attributes: list[BaseAttribute],
        children: list[BranchSpecT],
    ):
        assert isinstance(self, BaseDeclarativeNote)

        children.append(
            cast(
                BranchSpecT,
                (child, {"prefix": prefix, "expanded": expanded}),
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
        init_decl_old = cls._init_decl

        @wraps(init_decl_old)
        def _init_decl(
            self,
            cls_decl,
            attributes: list[BaseAttribute],
            children: list[BranchSpecT],
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
