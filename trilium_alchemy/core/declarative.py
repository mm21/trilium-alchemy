"""
Decorators to add attributes and children declaratively.

```{todo}
Configuration of {obj}`Session` to ignore changes to 
{obj}`Branch.expanded` as this is mostly a UI concept. It can be clobbered
as children of {obj}`Note` subclasses force setting {obj}`Branch.expanded`.
```
"""

from __future__ import annotations

import importlib.resources
import inspect
import os
from abc import ABC, ABCMeta
from functools import wraps
from types import ModuleType
from typing import IO, Any, Iterable, Literal, Self, cast

from .attribute import BaseAttribute, Label, Relation
from .branch import Branch
from .entity import BaseEntity
from .note.note import BranchSpecT, InitContainer, Note, id_hash, is_string
from .session import SessionContainer

__all__ = [
    "BaseDeclarativeNote",
    "BaseDeclarativeMixin",
    "label",
    "relation",
    "label_def",
    "relation_def",
    "children",
    "child",
]
__canonical_syms__ = __all__


class DeclarativeMeta(ABCMeta):
    """
    To generate documentation for added attributes and children, use
    initialize the list of descriptions for decorators added to it.
    """

    def __new__(cls, name, bases, attrs) -> Self:
        attrs["_decorator_doc"] = []

        # add decorators from bases first
        for base in bases:
            if hasattr(base, "_decorator_doc"):
                attrs["_decorator_doc"] += base._decorator_doc

        return super().__new__(cls, name, bases, attrs)


class BaseDeclarativeMixin(
    ABC,
    SessionContainer,
    metaclass=DeclarativeMeta,
):
    """
    Reusable collection of attributes and children which can be inherited by a
    {obj}`BaseDeclarativeNote`.
    """

    icon: str | None = None
    """
    If provided, adds `#iconClass` label unless it is already present.
    """

    _sequence_map: dict[type, dict[str, int]]
    """
    State to keep track of sequence numbers for deterministic attribute/
    child ids.
    """

    _note: BaseDeclarativeNote

    _note_id: str | None = None
    """
    Explicitly set note_id.
    """

    _note_id_seed_final: str | None
    """
    Note id seed, either provided explicitly or derived from parent.
    """

    _force_leaf: bool = False
    """
    If we applied the triliumAlchemyDeclarative CSS class to templates and
    their children, the user wouldn't be able to modify children of instances
    of that template in the UI since the cssClass would be inherited as well.

    This is a simple way to work around that by forcing this note to act as
    a leaf note for the purpose of checking whether to add the cssClass,
    even though we still want to maintain the template itself declaratively.
    """

    def init(
        self,
        attributes: list[BaseAttribute],
        children: list[Note | type[Note] | Branch],
    ):
        """
        Can be overridden to add attributes and/or children during
        instantiation. Use the following to create attribute/child with
        deterministic id:

        - {obj}`BaseDeclarativeMixin.create_declarative_label`
        - {obj}`BaseDeclarativeMixin.create_declarative_relation`
        - {obj}`BaseDeclarativeMixin.create_declarative_child`

        ```{note}
        User should **not** invoke `super().init()`{l=python}.
        To add attributes and children in an intuitive order,
        TriliumAlchemy manually traverses a {obj}`Note` subclass's MRO and invokes
        decorator-patched inits followed by {obj}`BaseDeclarativeMixin.init`.
        ```
        """
        if self.icon and all(a.name != "iconClass" for a in attributes):
            attributes.append(
                self.create_declarative_label("iconClass", self.icon)
            )

    def create_declarative_label(
        self, name: str, value: str = "", inheritable: bool = False
    ) -> Label:
        """
        Create and return a {obj}`Label` with deterministic `attribute_id`
        based on its `name` and note's `note_id`. Should be used in
        subclassed {obj}`BaseDeclarativeNote.init` or
        {obj}`BaseDeclarativeMixin.init` to generate the same `attribute_id`
        upon every instantiation.

        Multiple attributes of the same name are supported.
        """
        attribute_id = self._derive_id(Label, name)
        return Label(
            name,
            value=value,
            inheritable=inheritable,
            session=self._session,
            attribute_id=attribute_id,
            owning_note=self,
        )

    def create_declarative_relation(
        self, name: str, target: Note, inheritable: bool = False
    ) -> Relation:
        """
        Create and return a {obj}`Relation` with deterministic `attribute_id`
        based on its `name` and note's `note_id`. Should be used in
        subclassed {obj}`BaseDeclarativeNote.init` or
        {obj}`BaseDeclarativeMixin.init` to generate the same `attribute_id`
        upon every instantiation.

        Multiple attributes of the same name are supported.
        """
        attribute_id = self._derive_id(Relation, name)
        return Relation(
            name,
            target,
            inheritable=inheritable,
            session=self._session,
            attribute_id=attribute_id,
            owning_note=self,
        )

    def create_declarative_child(
        self, child_cls: type[BaseDeclarativeNote], **kwargs
    ) -> Branch:
        """
        Create a child {obj}`Note` with deterministic `note_id` and return a
        {obj}`Branch`. Should be used in subclassed
        {obj}`Note.init` or {obj}`BaseDeclarativeMixin.init` to generate
        the same child `note_id` upon every instantiation.

        Instantiate provided class as a declarative child of the current
        note by generating a deterministic id and returning the
        corresponding branch.

        If the parent note's note_id is not set, the child note's may not be.
        If the child's note_id is not set, a new note will be created upon
        every instantiation. This is the case for non-singleton subclasses.
        """
        child_decl_id: tuple[str, str | None] | None = child_cls._get_decl_id(
            self._note
        )

        child_note_id: str | None = None
        child_note_id_seed_final: str | None = None

        if child_decl_id is not None:
            child_note_id, child_note_id_seed_final = child_decl_id

        child: Note = child_cls(
            note_id=child_note_id,
            session=self._session,
            force_leaf=self._force_leaf,
            note_id_seed_final=child_note_id_seed_final,
            **kwargs,
        )

        return self._normalize_child(child)

    def _init_decl_mixin(
        self,
        note: BaseDeclarativeNote,
        note_id: str | None,
        note_id_seed_final: str | None,
        force_leaf: bool,
    ):
        self._note = note
        self._note_id = note_id
        self._note_id_seed_final = note_id_seed_final

        # get from parent if True
        if force_leaf is True:
            self._force_leaf = force_leaf

        self._sequence_map = {}

    def _get_sequence(self, cls: type[BaseEntity], base: str):
        """
        Get entity id sequence number given entity type and a base name,
        e.g. note id seed or attribute name.
        """

        if cls not in self._sequence_map:
            self._sequence_map[cls] = dict()

        if base in self._sequence_map[cls]:
            self._sequence_map[cls][base] += 1
        else:
            self._sequence_map[cls][base] = 0

        return self._sequence_map[cls][base]

    def _derive_id(self, cls: type[BaseEntity], base: str) -> str | None:
        """
        Generate a declarative entity id unique to this note with namespace
        per entity type.

        Increments a sequence number per base, so e.g. there can be
        multiple attributes with the same name.
        """
        id_seed: str | None = self._derive_id_seed(cls, base)
        return id_hash(id_seed) if id_seed is not None else None

    def _derive_id_seed(self, cls: type[BaseEntity], base: str) -> str | None:
        """
        Attempt to derive id seed for the provided entity based on this note.
        """

        # derive from parent's final note_id_seed if possible,
        # fall back to note_id
        prefix: str | None = self._note_id_seed_final or self._note_id

        if prefix is not None:
            sequence = self._get_sequence(cls, base)
            suffix = "" if sequence == 0 else f"_{sequence}"

            return f"{prefix}/{base}{suffix}"

        return None

    def _init_mixin(self) -> tuple[list[BaseAttribute], list[BranchSpecT]]:
        """
        Invoke declarative init and return tuple of attributes and children.
        """

        attributes: list[BaseAttribute] = []
        children: list[BranchSpecT] = []

        # traverse MRO to add attributes and children in an intuitive order.
        # for each class in the MRO:
        # - add decorator-based attributes/children
        # - add init()-based attributes/children
        # a nice side effect of this is the user doesn't have to invoke
        # super().init()
        for cls in type(self).mro():
            if issubclass(cls, BaseDeclarativeMixin):
                # invoke init chain added by decorators
                cls._init_decl(self, cls, attributes, children)

                # invoke manually implemented init()
                if not is_inherited(cls, "init"):
                    cls.init(
                        self,
                        attributes,
                        cast(list[Note | type[Note] | Branch], children),
                    )

        return attributes, children

    def _normalize_child(self, child: Note | Branch) -> Branch:
        """
        Take child as Note or Branch and return a Branch.
        """

        if isinstance(child, Note):
            # check if ids are known
            if self._note_id is not None:
                # if ids are known at this point, also generate branch id
                branch_id = f"{self._note_id}_{child.note_id}"
            else:
                branch_id = None

            return Branch(
                parent=self._note,
                child=child,
                branch_id=branch_id,
                session=self._session,
            )
        else:
            # ensure we have a Branch
            assert isinstance(child, Branch)
            return child

    def _normalize_branch(self, branch_spec: BranchSpecT) -> Branch:
        """
        Take child as BranchSpecT and return a Branch.
        """
        branch: Branch
        child_spec: Note | type[Note] | Branch
        branch_kwargs: dict

        # extract branch args if provided
        if isinstance(branch_spec, tuple):
            child_spec, branch_kwargs = branch_spec
        else:
            child_spec = branch_spec
            branch_kwargs = dict()

        if issubclass(type(child_spec), DeclarativeMeta):
            # have Note class
            child_cls: type[BaseDeclarativeNote] = cast(
                type[BaseDeclarativeNote], child_spec
            )
            branch = self.create_declarative_child(child_cls)
        else:
            # have Note or Branch
            assert isinstance(child_spec, Note) or isinstance(
                child_spec, Branch
            )
            branch = self._normalize_child(child_spec)

        # set branch kwargs
        for key, value in branch_kwargs.items():
            setattr(branch, key, value)

        return branch

    def _normalize_children(self, children: list[BranchSpecT]) -> list[Branch]:
        """
        Instantiate any Note classes provided and normalize as child Branch.
        """
        return [self._normalize_branch(branch_spec) for branch_spec in children]

    # Base declarative init method which can be patched by decorators
    def _init_decl(
        self,
        cls_decl: type[BaseDeclarativeMixin],
        attributes: list[BaseAttribute],
        children: list[BranchSpecT],
    ):
        pass


class BaseDeclarativeNote(Note, BaseDeclarativeMixin):
    """
    Note to use as subclass for declarative notes, i.e. note classes which
    automatically sync with the corresponding note if it already exists
    in Trilium.

    ```{todo}
    Add `auto_mime=True`{l=python} to also set `mime` using `magic` package
    (or do so automatically if {obj}`Note.content_file` set, but
    {obj}`Note.mime` not set)
    ```
    """

    decl_note_id: str | None = None
    """
    `note_id` to explicitly assign.
    """

    decl_title: str | None = None
    """
    Title to set, or `None` to use class name.
    """

    decl_note_type: str | None = None
    """
    Note type to set.
    """

    decl_mime: str | None = None
    """
    MIME type to set.
    """

    decl_content: str | bytes | IO | None = None
    """
    Content to set.
    """

    content_file: str | None = None
    """
    Name of file to use as content, relative to module's location. Also adds
    `#originalFilename` label.

    ```{note}
    Currently Trilium only shows `#originalFilename` if the note's type is
    `file`.
    ```
    """

    note_id_seed: str | None = None
    """
    Seed from which to generate `note_id`. Useful to generate a
    collision-avoidant id from a human-friendly identifier.
    Generated as base64-encoded hash of seed.

    If you want to fix the id of a subclassed note, it's recommended
    to use {obj}`BaseDeclarativeMixin.singleton`, which internally generates
    {obj}`BaseDeclarativeMixin.note_id_seed` from the class name. However if you
    want `note_id` to be invariant of where the class is located in
    its package, you may prefer to use {obj}`BaseDeclarativeMixin.note_id_seed`
    directly.
    """

    note_id_segment: str | None = None
    """
    Segment with which to generate `note_id` given the parent's `note_id`,
    if no `note_id` is otherwise specified.
    """

    singleton: bool = False
    """
    If set on a {obj}`Note` subclass, enables deterministic calculation
    of `note_id` based on the fully qualified class name. This means the same
    class will always have the same `note_id` when instantiated.

    ```{warning}
    If you move this class to a different module, it will result in a different
    `note_id` which will break any non-declarative relations to it. 
    To enable more portable behavior, set `idempotent` or assign a 
    `note_id_seed` explicitly.
    ```
    """

    idempotent: bool = False
    """
    If set on a {obj}`Note` subclass, enables deterministic calculation
    of `note_id` based on the class name. Similar to `singleton`, but only
    the class name (not fully qualified) is used.
    """

    idempotent_segment: bool = False
    """
    If set on a {obj}`Note` subclass, sets segment name to class name
    for the purpose of `note_id` calculation. 
    An explicitly provided {obj}`BaseDeclarativeMixin.note_id_segment` takes precedence.
    """

    leaf: bool = False
    """
    If set to `True`{l=python} on a {obj}`Note` subclass, disables setting
    of child notes declaratively, allowing children to be manually
    maintained by the user. Otherwise, notes added by the user will be
    deleted to match the children added declaratively.

    Should be set on notes intended to hold user notes, e.g. todo lists.

    If `False`{l=python} and `note_id` is deterministically generated (e.g.
    it's a singleton or child of a singleton), a label
    `#cssClass=triliumAlchemyDeclarative` is added by TriliumAlchemy.
    This enables hiding of the "Add child note" button in Trilium's UI
    via the {obj}`AppCss` note added by {obj}`BaseRootSystemNote`.
    """

    hide_new_note: bool = False
    """
    Whether to hide "new note" button, regardless of whether it would otherwise
    be hidden. Can be used to hide "new note" button for e.g. 
    {obj}`Templates` which otherwise would show it.
    """

    _stem_title: bool = False
    """
    Whether to take the title as the stem of the filename.
    """

    @property
    def note_id_seed_final(self) -> str | None:
        """
        Get the seed from which this note's id was derived. Useful for
        debugging.
        """
        return self._note_id_seed_final

    @classmethod
    def _is_singleton(cls) -> bool:
        return cls._get_decl_id() is not None

    @classmethod
    def _get_note_id(cls, note_id: str | None) -> tuple[str | None, str | None]:
        note_id_seed_final: str | None = None

        if note_id is None:
            # try to get declarative note id
            decl_id: tuple[str, str | None] | None = cls._get_decl_id()

            if decl_id is not None:
                note_id, note_id_seed_final = decl_id

        return note_id, note_id_seed_final

    def _init_hook(
        self,
        note_id: str | None,
        note_id_seed_final: str | None,
        force_leaf: bool | None,
    ) -> InitContainer:
        super()._init_decl_mixin(self, note_id, note_id_seed_final, force_leaf)

        container = InitContainer()

        # set fields from subclass
        container.note_type = self.decl_note_type or "text"
        container.mime = self.decl_mime or "text/html"
        container.content = self.decl_content

        # invoke init chain defined on mixin
        attributes, children = self._init_mixin()

        if self.leaf:
            # leaf note: make sure there are no declarative children
            # - leaf note means the user manually maintains children in UI
            # or syncs from a folder
            assert (
                len(children) == 0
            ), f"Attempt to declaratively update children of leaf note {self}, {type(self)}: {children}"

        # check if content is set by file
        if self.content_file is not None:
            assert (
                self.decl_content is None
            ), f"Attempt to set content from both file {self.content_file} and decl_content attribute"

            # add originalFilename label if content set from file
            attributes += [
                self.create_declarative_label(
                    "originalFilename",
                    value=os.path.basename(self.content_file),
                )
            ]

            container.content = self._get_content_fh(
                container.note_type, container.mime
            )

            if self._stem_title:
                container.title = os.path.basename(self.content_file).split(
                    "."
                )[0]

        container.title = (
            container.title or self.decl_title or type(self).__name__
        )

        # add #cssClass for internal (non-leaf) singleton declarative
        # notes which aren't templates. this enables hiding
        # "create child" button (templates should always be modifiable
        # since the cssClass would be inherited to instances created
        # by user)
        if note_id is not None:
            if self.hide_new_note or not any([self.leaf, self._force_leaf]):
                attributes.append(
                    self.create_declarative_label(
                        "cssClass", value="triliumAlchemyDeclarative"
                    )
                )

        container.attributes = attributes
        container.children = self._normalize_children(children)

        return container

    @classmethod
    def _get_decl_id(
        cls, parent: BaseDeclarativeNote | None = None
    ) -> tuple[str, str | None] | None:
        """
        Try to get a note_id. If one is returned, this note has a deterministic
        note_id and will get the same one every time it's instantiated.
        """

        module: ModuleType | None = inspect.getmodule(cls)
        assert module is not None

        if cls.decl_note_id is not None:
            return (cls.decl_note_id, None)

        # get fully qualified class name
        fqcn = f"{module.__name__}.{cls.__name__}"

        # attempt to get id seed
        note_id_seed: str | None = cls._get_note_id_seed(fqcn, parent)

        if note_id_seed is not None:
            # child note_id derived by seed
            return id_hash(note_id_seed), note_id_seed

        return None

    @classmethod
    def _get_note_id_seed(
        cls, fqcn: str, parent: BaseDeclarativeNote | None
    ) -> str | None:
        """
        Get the seed used to generate `note_id` for this subclass.
        """
        if cls.note_id_seed:
            # seed provided
            return cls.note_id_seed
        elif cls.idempotent:
            # get seed from class name (not fully-qualified)
            return cls.__name__
        elif cls.singleton:
            # get id from fully-qualified class name
            return fqcn
        elif parent is not None:
            # not declared as singleton, but possibly created by
            # singleton parent, so try to generate deterministic id

            # select base as provided segment or fully-qualified class name
            base: str
            if cls.idempotent_segment:
                # base is class name (not fully-qualified)
                base = cls.__name__
            else:
                # base is segment if provided, else fully-qualified class name
                base = cls.note_id_segment or fqcn

            return parent._derive_id_seed(BaseDeclarativeNote, base)

        return None

    # Return class which specified content_file
    def _get_content_cls(self):
        for cls in type(self).mro():
            if issubclass(cls, BaseDeclarativeNote) and cls.content_file:
                return cls

    # Return handle of file specified by content_file
    def _get_content_fh(self, note_type: str, mime: str) -> IO:
        # get class which defined content_file
        cls = self._get_content_cls()
        assert cls is not None

        # get path to content from class
        module = inspect.getmodule(cls)
        content_path: str

        assert module is not None
        assert self.content_file is not None

        try:
            # assume we're in a package context
            # (e.g. trilium_alchemy installation)
            module_path = module.__name__.split(".")

            content_file = self.content_file.split("/")
            basename = content_file[-1]
            module_rel = content_file[:-1]

            try:
                module.__module__
            except AttributeError:
                # have a package
                pass
            else:
                # have a module, we want a package
                del module_path[-1]

            module_content = ".".join(module_path + module_rel)
            content_path = str(
                importlib.resources.files(module_content) / basename
            )

        except ModuleNotFoundError as e:
            # not in a package context (e.g. test code, standalone script)
            path_folder = os.path.dirname(str(module.__file__))
            content_path = os.path.join(path_folder, self.content_file)

        assert os.path.isfile(
            content_path
        ), f"Content file specified by {cls} does not exist: {content_path}"

        mode = "r" if is_string(note_type, mime) else "rb"
        return open(content_path, mode)


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
        attributes += [
            self.create_declarative_label(
                name, value=value, inheritable=inheritable
            )
        ]

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
    :param target_cls: Class of relation target, will be instantiated when this note is instantiated (so it must have {obj}`BaseDeclarativeMixin.singleton`, {obj}`BaseDeclarativeMixin.note_id`, or {obj}`BaseDeclarativeMixin.note_id_seed` set)
    :param inheritable: Whether relation should be inherited to children
    :param accumulate: Whether relation should be added if an attribute with this name already exists from a subclassed {obj}`BaseDeclarativeNote` or {obj}`BaseDeclarativeMixin`
    """

    @check_name(name, accumulate=accumulate)
    def init(
        self, attributes: list[BaseAttribute], children: list[BranchSpecT]
    ):
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
        self, attributes: list[BaseAttribute], children_: list[BranchSpecT]
    ):
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
        self, attributes: list[BaseAttribute], children: list[BranchSpecT]
    ):
        children.append(
            cast(
                BranchSpecT,
                (child, {"prefix": prefix, "expanded": expanded}),
            )
        )

    return _patch_init_decl(init)


def is_inherited(cls: type[BaseDeclarativeMixin], attr: str) -> bool:
    """
    Check if given attribute is inherited from superclass (True) or defined on this
    class (False).
    """
    value = getattr(cls, attr)
    return any(
        value is getattr(cls_super, attr, object())
        for cls_super in cls.__bases__
    )


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
