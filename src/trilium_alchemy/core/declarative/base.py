from __future__ import annotations

import importlib.resources
import inspect
import os
from abc import ABC, ABCMeta
from types import ModuleType
from typing import IO, Iterable, Self

from ..attribute import BaseAttribute, Label, Relation
from ..branch import Branch
from ..entity import BaseEntity
from ..note.note import InitContainer, Note, id_hash, is_string
from ..session import SessionContainer

__all__ = [
    "BaseDeclarativeNote",
    "BaseDeclarativeMixin",
]


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
        children: list[Branch],
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
        TriliumAlchemy manually traverses a {obj}`BaseDeclarativeNote`
        subclass's MRO and invokes decorator-patched inits followed by
        {obj}`BaseDeclarativeMixin.init`.
        ```

        :param attributes: List of attributes to which user can append using {obj}`BaseDeclarativeMixin.create_declarative_label` or {obj}`BaseDeclarativeMixin.create_declarative_relation`
        :param children: List of children to which user can append using {obj}`BaseDeclarativeMixin.create_declarative_child`
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
            _attribute_id=attribute_id,
            _owning_note=self,
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
            _attribute_id=attribute_id,
            _owning_note=self,
        )

    def create_declarative_child(
        self,
        child_cls: type[BaseDeclarativeNote],
        title: str | None = None,
        note_type: str | None = None,
        mime: str | None = None,
        parents: Iterable[Note | Branch] | Note | Branch | None = None,
        children: Iterable[Note | Branch] | None = None,
        attributes: Iterable[BaseAttribute] | None = None,
        content: str | bytes | IO | None = None,
        template: Note | type[Note] | None = None,
        prefix: str = "",
        expanded: bool | None = None,
    ) -> Branch:
        """
        Creates a child {obj}`BaseDeclarativeNote` with deterministic
        `note_id` and returns a {obj}`Branch`. Should be used in subclassed
        {obj}`BaseDeclarativeNote.init` or {obj}`BaseDeclarativeMixin.init`
        to generate the same child `note_id` upon every instantiation.

        If the parent note's `note_id` set, the child note will be assigned
        one so as to create the same `note_id` upon every instantiation.

        If the child's `note_id` is not fixed, a new note will be created upon
        every instantiation. This is the case for non-singleton subclasses.

        Params following `child_cls` are passed to the `Note` and `Branch`
        initializers.

        :param child_cls: Class of child to instantiate
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
            title=title,
            note_type=note_type,
            mime=mime,
            parents=parents,
            children=children,
            attributes=attributes,
            content=content,
            template=template,
            _force_leaf=self._force_leaf,
            _note_id_seed_final=child_note_id_seed_final,
        )

        # check if ids are known
        if self._note_id and child_note_id:
            # if ids are known at this point, also generate branch id
            branch_id = Branch._gen_branch_id(self._note_id, child_note_id)
        else:
            branch_id = None

        branch = Branch(
            parent=self._note,
            child=child,
            prefix=prefix,
            session=self._session,
            _branch_id=branch_id,
            _ignore_expanded=True,
        )

        if expanded is not None:
            branch.expanded = expanded

        return branch

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

    def _init_mixin(
        self,
    ) -> tuple[list[BaseAttribute], list[Branch]]:
        """
        Invoke declarative init and return tuple of attributes and children.
        """

        attributes: list[BaseAttribute] = []
        children: list[Branch] = []

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
                        children,
                    )

        # validate
        for attr in attributes:
            assert isinstance(
                attr, (Label, Relation)
            ), f"Got unexpected attribute type: {type(attr)}, {attr}"
        for branch in children:
            assert isinstance(
                branch, Branch
            ), f"Got unexpected child type: {type(branch)}, {branch}"

        return attributes, children

    # Base declarative init method which can be patched by decorators
    def _init_decl(
        self,
        cls_decl: type[BaseDeclarativeMixin],
        attributes: list[BaseAttribute],
        children: list[Branch],
    ):
        pass


class BaseDeclarativeNote(Note, BaseDeclarativeMixin):
    """
    Note to use as subclass for declarative notes, i.e. note classes which
    automatically sync with the corresponding note if it already exists
    in Trilium.

    ```{note}
    Subclassing this class means the note will replace any existing fields
    (title, type, mime, content) as well as attributes and children.
    Set `leaf = True` to preserve children.
    ```

    ```{todo}
    Add `auto_mime=True`{l=python} to also set `mime` using `magic` package
    (or do so automatically if `BaseDeclarativeNote.content_file` set, but
    `BaseDeclarativeNote.mime_` not set)
    ```
    """

    note_id_: str | None = None
    """
    `note_id` to explicitly assign.
    """

    title_: str | None = None
    """
    Title to set, or `None` to use class name.
    """

    note_type_: str | None = None
    """
    Note type to set.
    """

    mime_: str | None = None
    """
    MIME type to set.
    """

    content_: str | bytes | IO | None = None
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
    """

    note_id_segment: str | None = None
    """
    Segment with which to generate `note_id` given the parent's `note_id`,
    if no `note_id` is otherwise specified.
    """

    singleton: bool = False
    """
    If set on a {obj}`BaseDeclarativeNote` subclass, enables deterministic 
    calculation of `note_id` based on the fully qualified class name. 
    This means the same class will always have the same `note_id` when 
    instantiated.

    ```{warning}
    If you move this class to a different module, it will result in a different
    `note_id` which will break any non-declarative relations to it. 
    To enable more portable behavior, set 
    {obj}`BaseDeclarativeNote.idempotent` or assign 
    {obj}`BaseDeclarativeNote.note_id_seed` explicitly.
    ```
    """

    idempotent: bool = False
    """
    If set on a {obj}`BaseDeclarativeNote` subclass, enables deterministic 
    calculation of `note_id` based on the class name. Similar to 
    {obj}`BaseDeclarativeNote.singleton`, but only the class name 
    (not fully qualified) is used.
    """

    idempotent_segment: bool = False
    """
    If set on a {obj}`BaseDeclarativeNote` subclass, sets segment name to 
    class name for the purpose of `note_id` calculation. 
    An explicitly provided {obj}`BaseDeclarativeNote.note_id_segment` 
    takes precedence.
    """

    leaf: bool = False
    """
    If set to `True`{l=python} on a {obj}`BaseDeclarativeNote` subclass,
    disables setting of child notes declaratively, allowing children to be 
    manually maintained by the user. Otherwise, notes added by the user will be
    deleted to match the children added declaratively.

    Should be set on notes intended to hold user notes, e.g. todo lists.
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

    _force_position_cleanup: bool = True

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
        container.note_type = self.note_type_ or "text"
        container.mime = self.mime_
        container.content = self.content_

        # invoke init chain defined on mixin
        attributes, children = self._init_mixin()

        if self.leaf:
            # leaf note: make sure there are no declarative children
            # - leaf note means the user maintains children in UI
            if len(children):
                raise ValueError(
                    f"Attempt to declaratively update children of leaf note {self}, {type(self)}: {children}"
                )

        # check if content is set by file
        if self.content_file is not None:
            assert (
                self.content_ is None
            ), f"Attempt to set content from both file {self.content_file} and content_ attribute"

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

        container.title = container.title or self.title_ or type(self).__name__

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

        # add #triliumAlchemyDeclarativeLeaf for leaf singleton declarative
        # notes, allowing the user to e.g. selectively dump them to filesystem
        if note_id is not None and self.leaf:
            attributes.append(
                self.create_declarative_label("triliumAlchemyDeclarativeLeaf")
            )

        container.attributes = attributes

        if not self.leaf:
            container.children = children

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

        if cls.note_id_ is not None:
            return (cls.note_id_, None)

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

        except ModuleNotFoundError:
            # not in a package context (e.g. test code, standalone script)
            path_folder = os.path.dirname(str(module.__file__))
            content_path = os.path.join(path_folder, self.content_file)

        assert os.path.isfile(
            content_path
        ), f"Content file specified by {cls} does not exist: {content_path}"

        mode = "r" if is_string(note_type, mime) else "rb"
        return open(content_path, mode)


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
