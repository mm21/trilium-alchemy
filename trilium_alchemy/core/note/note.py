from __future__ import annotations

import base64
import hashlib
import importlib.resources
import inspect
import logging
import os
from abc import ABC, ABCMeta
from collections.abc import Iterable, MutableMapping
from functools import wraps
from types import ModuleType
from typing import IO, Any, Generic, Iterator, Literal, TypeVar, Union, cast

from trilium_client.models.note import Note as EtapiNoteModel

from ..attribute import Attribute, Label, Relation
from ..branch import Branch
from ..entity.entity import Entity, EntityIdDescriptor, normalize_entities

# isort: off
from ..entity.model import (
    Model,
    FieldDescriptor,
    ReadOnlyFieldDescriptor,
    ExtensionDescriptor,
    require_model,
)

# isort: on

from ..exceptions import _assert_validate
from ..session import Session, SessionContainer, require_session
from .attributes import Attributes, ValueSpec
from .branches import Branches, Children, Parents
from .content import Content, ContentDescriptor
from .model import NoteModel

__all__ = [
    "Note",
    "Mixin",
]


# TODO: find out why references to TypeVars can't be resolved in API docs,
# then this can be used in API (e.g. @children)
# TODO: encapsulate "Note" | type["Note"] | Branch
BranchSpecT = TypeVar(
    "BranchSpecT",
    bound=Union[
        "Note",
        type["Note"],
        Branch,
        tuple[Union["Note", type["Note"], Branch], dict[str, Any]],
    ],
)
"""
Specifies a branch to be declaratively added as child. May be:

- {obj}`Note` instance
- {obj}`Note` subclass
- {obj}`Branch` instance
- Tuple of `(Note|type[Note]|Branch, dict[str, Any])`{l=python} with dict providing branch kwargs
"""

STRING_NOTE_TYPES = {
    "text",
    "code",
    "relationMap",
    "search",
    "render",
    "book",
    "mermaid",
    "canvas",
}
"""
Keep in sync with isStringNote() (src/services/utils.js).
"""

STRING_MIME_TYPES = {
    "application/javascript",
    "application/x-javascript",
    "application/json",
    "application/x-sql",
    "image/svg+xml",
}
"""
Keep in sync with STRING_MIME_TYPES (src/services/utils.js).
"""


def is_string(note_type: str, mime: str) -> bool:
    """
    Encapsulates logic for checking if a note is considered string type
    according to Trilium.

    This should be kept in sync with src/services/utils.js:isStringNote()
    """
    return (
        note_type in STRING_NOTE_TYPES
        or mime.startswith("text/")
        or mime in STRING_MIME_TYPES
    )


def require_note_id(func):
    # ent: may be cls or self
    @wraps(func)
    def _declarative_note_id(ent, *args, **kwargs):
        if "note_id" not in kwargs:
            kwargs["note_id"] = None

        # get declarative note id
        if kwargs["note_id"] is None:
            kwargs["note_id"] = get_cls(ent)._get_decl_id()
            note_id = kwargs["note_id"]

        return func(ent, *args, **kwargs)

    return _declarative_note_id


def patch_init(init, doc: str | None = None):
    """
    Insert provided init function in class's declarative init sequence.
    """

    def _patch_init(cls):
        init_decl_old = cls._init_decl

        @wraps(init_decl_old)
        def _init_decl(
            self,
            cls_decl,
            attributes: list[Attribute],
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

    return _patch_init


def id_hash(seed: str) -> str:
    """
    Return id given seed. Needed to ensure IDs have a consistent amount of
    entropy by all being of the same length and character distribution.

    Note: there is a small loss in entropy due to mapping the characters '+'
    and '/' to 'a' and 'b' respectively. This is required since these are not
    allowable characters in Trilium and will result in a slight bias,
    compromising cryptographic properties, but it's inconsequential
    for this application.

    They could be replaced with e.g. 'aa', 'ab' to restore cryptographic
    entropy, but at the cost of making IDs inconsistent lengths.
    """
    hex_string = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    byte_string = bytes.fromhex(hex_string)
    condensed_string = (
        base64.b64encode(byte_string)
        .decode("utf-8")
        .replace("=", "")
        .replace("+", "a")
        .replace("/", "b")
    )
    return condensed_string


def get_cls(ent: Note | type[Note]) -> type[Note]:
    """
    Check if note is a class or instance and return the class.
    """
    if isinstance(ent, BaseMeta):
        # have class
        return cast(type[Note], ent)
    # have instance
    return cast(type[Note], type(ent))


def is_inherited(cls: type[Mixin], attr: str) -> bool:
    """
    Check if given attribute is inherited from superclass (True) or defined on this
    class (False).
    """
    value = getattr(cls, attr)
    return any(
        value is getattr(cls_super, attr, object())
        for cls_super in cls.__bases__
    )


class BaseMeta(ABCMeta):
    """
    Use metaclass for Mixin to initialize list of descriptions for
    decorators added to it. Inherits decorator docs from bases.
    Otherwise subclasses will add decorator docs to their bases also.

    Also get fields (title/type/mime) from subclassed Mixin
    and rename them to avoid collision with descriptors.

    This way subclasses can intuitively set e.g. 'title' rather than
    'title_'.
    """

    def __new__(cls, name, bases, attrs):
        attrs["_decorator_doc"] = []

        # add decorators from bases first
        for base in bases:
            if hasattr(base, "_decorator_doc"):
                attrs["_decorator_doc"] += base._decorator_doc

        if bases[0] not in {Entity, ABC}:
            # subclass of Note or Mixin

            # check if any model fields are defined on class
            for field in NoteModel.fields_update_alias + ["note_id"]:
                if field in attrs:
                    # rename them
                    field_new = f"{field}_"
                    attrs[field_new] = attrs[field]
                    del attrs[field]

        return super().__new__(cls, name, bases, attrs)


class NoteMeta(BaseMeta):
    """
    Additionally wrap __init__ to take defaults as None. This is needed to
    avoid clobbering title/type/mime for existing notes, but still
    document the defaults for new note creation in the API.
    """

    def __new__(cls, name, bases, attrs):
        note_cls = super().__new__(cls, name, bases, attrs)
        cls_init = note_cls.__init__

        @wraps(cls_init)
        def __init__(self, *args, **kwargs):
            for field in NoteModel.fields_update_alias:
                if field not in kwargs:
                    kwargs[field] = None

            cls_init(self, *args, **kwargs)

        note_cls.__init__ = __init__  # type: ignore

        return note_cls


class Mixin(
    ABC,
    SessionContainer,
    Generic[BranchSpecT],
    metaclass=BaseMeta,
):
    """
    Reusable collection of attributes, children, and fields
    (`note_id`, `title`, `type`, `mime`) which can be inherited by a
    {obj}`Note`.

    ```{note}
    Since {obj}`Note` inherits from {obj}`Mixin`, any {obj}`Note`
    subclass is also a valid {obj}`Mixin` and can use the same semantics
    to set attributes/children/fields.
    ```

    ```{todo}
    Add `auto_mime=True`{l=python} to also set `mime` using `magic` package
    (or do so automatically if {obj}`Mixin.content_file` set, but
    {obj}`Mixin.mime` not set)
    ```
    """

    note_id: str | None = None
    """
    `note_id` to explicitly assign.
    """

    note_id_seed: str | None = None
    """
    Seed from which to generate `note_id`. Useful to generate a
    collision-avoidant id from a human-friendly identifier.
    Generated as base64-encoded hash of seed.

    If you want to fix the id of a subclassed note, it's recommended
    to use {obj}`Mixin.singleton`, which internally generates
    {obj}`Mixin.note_id_seed` from the class name. However if you
    want `note_id` to be invariant of where the class is located in
    its package, you may prefer to use {obj}`Mixin.note_id_seed`
    directly.
    """

    note_id_segment: str | None = None
    """
    Segment with which to generate `note_id` given the parent's `note_id`,
    if no `note_id` is otherwise specified.
    """

    title: str | None = None
    """
    Sets {obj}`title <Note.title>` of {obj}`Note` subclass. If `None`{l=python},
    title is set to the class's `__name__`.
    """

    note_type: str = "text"
    """
    Sets {obj}`note_type <Note.note_type>` of {obj}`Note` subclass.
    """

    mime: str = "text/html"
    """
    Sets {obj}`mime <Note.mime>` of {obj}`Note` subclass.
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
    via the {obj}`AppCss` note added by {obj}`BaseRootSystem`.
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

    hide_new_note: bool = False
    """
    Whether to hide "new note" button, regardless of whether it would otherwise
    be hidden. Can be used to hide "new note" button for e.g. 
    {obj}`Templates` which otherwise would not hide it.
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

    _sequence_map: dict[type, dict[str, int]] | None = None
    """
    State to keep track of sequence numbers for deterministic attribute/
    child ids.
    """

    _child_id_seed: str | None = None

    def __init__(self, child_id_seed: str | None):
        self._sequence_map = dict()
        self._child_id_seed = child_id_seed

    def init(
        self,
        attributes: list[Attribute],
        children: list[Note | type[Note] | Branch],
    ) -> dict[str, Any] | None:
        """
        Optionally provided by {obj}`Note` or {obj}`Mixin` subclass
        to add attributes and/or children during instantiation. Use the
        following to create attribute/child with deterministic id:
        - {obj}`Mixin.create_declarative_label`
        - {obj}`Mixin.create_declarative_relation`
        - {obj}`Mixin.create_declarative_child`

        Can return a `dict` of other fields to update, e.g. `title`.

        ```{note}
        User should **not** invoke `super().init()`{l=python}.
        To add attributes and children in an intuitive order,
        TriliumAlchemy manually traverses a {obj}`Note` subclass's MRO and invokes
        decorator-patched inits followed by {obj}`Mixin.init`.
        ```
        """
        ...

    def create_declarative_label(
        self, name: str, value: str = "", inheritable: bool = False
    ) -> Label:
        """
        Create and return a {obj}`Label` with deterministic `attribute_id`
        based on its `name` and note's `note_id`. Should be used in
        subclassed {obj}`Note.init` or {obj}`Mixin.init` to generate
        the same `attribute_id` upon every instantiation.

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
        subclassed {obj}`Note.init` or {obj}`Mixin.init` to generate
        the same `attribute_id` upon every instantiation.

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
        self, child_cls: type[Note], **kwargs
    ) -> Branch:
        """
        Create a child {obj}`Note` with deterministic `note_id` and return a
        {obj}`Branch`. Should be used in subclassed
        {obj}`Note.init` or {obj}`Mixin.init` to generate
        the same child `note_id` upon every instantiation.

        Instantiate provided class as a declarative child of the current
        note by generating a deterministic id and returning the
        corresponding branch.

        If the parent note's note_id is not set, the child note's may not be.
        If the child's note_id is not set, a new note will be created upon
        every instantiation. This is the case for non-singleton subclasses.
        """
        child_note_id: str | None = child_cls._get_decl_id(self)

        child: Note = child_cls(
            note_id=child_note_id,
            session=self._session,
            force_leaf=self._force_leaf,
            **kwargs,
        )

        return self._normalize_child(child)

    def _normalize_child(self, child: Note | Branch) -> Branch:
        """
        Take child as Note or Branch and return a Branch.
        """

        if isinstance(child, Note):
            # check if ids are known
            if self.note_id is not None:
                # if ids are known at this point, also generate branch id
                branch_id = Branch._gen_branch_id(cast(Note, self), child)
            else:
                branch_id = None

            return Branch(
                parent=cast(Note, self),
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
            # child, branch_kwargs = cast(
            #    tuple[Note | type[Note] | Branch, dict[str, Any]], branch_spec
            # )
            child_spec, branch_kwargs = branch_spec
        else:
            child_spec = cast(Note | type[Note] | Branch, branch_spec)
            branch_kwargs = dict()

        if isinstance(child_spec, type(Note)):
            # have Note class
            child_cls: type[Note] = cast(type[Note], child_spec)

            branch = self.create_declarative_child(child_cls)
        else:
            # have Note or Branch
            branch = self._normalize_child(cast(Note | Branch, child_spec))

        # set branch kwargs
        for key, value in branch_kwargs.items():
            setattr(branch, key, value)

        return branch

    def _normalize_children(self, children: list[BranchSpecT]) -> list[Branch]:
        """
        Instantiate any Note classes provided and normalize as child Branch.
        """
        return [self._normalize_branch(branch_spec) for branch_spec in children]

    # Invoke declarative init and return tuple of attributes, children
    def _init_mixin(
        self, fields_update: dict[str, Any]
    ) -> tuple[list[Attribute], list[BranchSpecT]]:
        attributes: list[Attribute] = list()
        children: list[BranchSpecT] = list()

        # traverse MRO to add attributes and children in an intuitive order.
        # for each class in the MRO:
        # - add decorator-based attributes/children
        # - add init()-based attributes/children
        # a nice side effect of this is the user doesn't have to invoke
        # super().init()
        for cls in type(self).mro():
            if issubclass(cls, Mixin):
                # invoke init chain added by decorators
                cls._init_decl(self, cls, attributes, children)

                # invoke manually implemented init()
                if not is_inherited(cls, "init"):
                    fields = cls.init(
                        self,
                        attributes,
                        cast(list[Note | type[Note] | Branch], children),
                    )
                    if fields:
                        # TODO: restrict fields which can be updated
                        fields_update.update(fields)

        return attributes, children

    # Base declarative init method which can be patched by decorators
    def _init_decl(
        self,
        cls_decl: type[Mixin],
        attributes: list[Attribute],
        children: list[BranchSpecT],
    ):
        pass

    # Return class which specified content_file
    def _get_content_cls(self):
        for cls in type(self).mro():
            if issubclass(cls, Mixin) and cls.content_file:
                return cls

    def _derive_id(self, cls: type[Entity], base: str) -> str | None:
        """
        Generate a declarative entity id unique to this note with namespace
        per class. Increments a sequence number per base, so e.g. there can be
        multiple attributes with the same name.
        """

        if self.note_id:
            # if child_id_seed was passed during init, use that to generate
            # deterministic child note id invariant of the root id.
            # this enables setting a tree of ids based on the app name rather
            # than the root note it's installed to
            if self._child_id_seed:
                prefix = self._child_id_seed
            else:
                prefix = self.note_id

            sequence = self._get_sequence(cls, base)
            return id_hash(f"{prefix}_{base}_{sequence}")

        return None

    def _get_sequence(self, cls, base):
        assert self._sequence_map is not None

        if cls not in self._sequence_map:
            self._sequence_map[cls] = dict()

        if base in self._sequence_map[cls]:
            self._sequence_map[cls][base] += 1
        else:
            self._sequence_map[cls][base] = 0

        return self._sequence_map[cls][base]


class Note(
    Entity[NoteModel],
    Mixin,
    MutableMapping,
    Generic[BranchSpecT],
    metaclass=NoteMeta,
):
    """
    Encapsulates a note and provides a base class for declarative notes.

    For a detailed walkthrough of how to use this class, see
    {ref}`Working with notes <working-with-notes-notes>`. Below summarizes a
    few of the features.

    It's first required to create a {obj}`Session` to connect to Trilium.
    These examples assume you've done so and assigned it to a variable
    `session`, and that you will invoke {obj}`session.flush() <Session.flush>`
    or use a context manager to commit changes.

    There are two fundamental ways of working with notes:

    ```{rubric} Imperative
    ```

    ```
    # create new note under root
    note = Note(title="My note", content="<p>Hello, world!</p>", parents=session.root)
    ```

    Use the `+=`{l=python} operator to add attributes and branches:

    ```
    # add label #sorted
    note += Label("sorted")

    # add child note with branch created implicitly
    note += Note(title="Child 1")

    # add child note with branch created explicitly
    note += Branch(child=Note(title="Child 2"))
    ```

    Use the clone operator `^=`{l=python} to add a note as a parent:

    ```
    # clone first child to root with branch created implicitly
    note.children[0] ^= session.root
    ```

    For single-valued attributes, you can get and set values by indexing
    into the note object using the attribute name as a key. This works
    for both labels and relations; the attribute type is inferred by the
    value set.

    ```
    # add label #hideChildrenOverview
    note["hideChildrenOverview"] = ""
    assert note["hideChildrenOverview"] == ""
    ```

    Check if a note has an attribute by using `in`{l=python}:

    ```
    assert "hideChildrenOverview" in note
    ```

    ```{rubric} Declarative
    ```

    You can declaratively specify a complete hierarchy of notes and their
    attributes. See {ref}`declarative-notes` for further discussion of this
    concept.

    ```
    class ChildNote(Note):
        title = "Child note"

    @label("sorted")
    @children(ChildNote)
    class MyNote(Note):
        title = "My note"
        content = "<p>Hello, world!</p>"

    # create new note under root
    note = MyNote(parents=session.root)
    assert note.title == "My note"
    ```
    """

    note_id: str | None = EntityIdDescriptor()  # type: ignore
    """
    Read-only access to `noteId`. Will be `None`{l=python} if
    newly created with no `note_id` specified and not yet flushed.
    """

    title: str = FieldDescriptor("title")  # type: ignore
    """
    Note title.
    """

    # TODO: custom descriptor for type w/validation
    note_type: str = FieldDescriptor("type")  # type: ignore
    """
    Note type.
    """

    mime: str = FieldDescriptor("mime")  # type: ignore
    """
    MIME type.
    """

    is_protected: bool = ReadOnlyFieldDescriptor("is_protected")  # type: ignore
    """
    Whether this note is protected.
    """

    date_created: str = ReadOnlyFieldDescriptor("date_created")  # type: ignore
    """
    Local created datetime, e.g. `2021-12-31 20:18:11.939+0100`.
    """

    date_modified: str = ReadOnlyFieldDescriptor("date_modified")  # type: ignore
    """
    Local modified datetime, e.g. `2021-12-31 20:18:11.939+0100`.
    """

    utc_date_created: str = ReadOnlyFieldDescriptor("utc_date_created")  # type: ignore
    """
    UTC created datetime, e.g. `2021-12-31 19:18:11.939Z`.
    """

    utc_date_modified: str = ReadOnlyFieldDescriptor("utc_date_modified")  # type: ignore
    """
    UTC modified datetime, e.g. `2021-12-31 19:18:11.939Z`.
    """

    attributes: Attributes = ExtensionDescriptor("_attributes")  # type: ignore
    """
    Interface to attributes, both owned and inherited.
    """

    branches: Branches = ExtensionDescriptor("_branches")  # type: ignore
    """
    Interface to branches, both parent and child.
    """

    parents: Parents = ExtensionDescriptor("_parents")  # type: ignore
    """
    Interface to parent notes.
    """

    children: Children = ExtensionDescriptor("_children")  # type: ignore
    """
    Interface to child notes.
    """

    content: str | bytes = ContentDescriptor("_content")  # type: ignore
    """
    Interface to note content. See {obj}`trilium_alchemy.core.note.content.Content`.
    """

    _model_cls = NoteModel

    # model extensions
    _attributes: Attributes
    _branches: Branches
    _parents: Parents
    _children: Children
    _content: Content

    @require_session
    @require_model
    @require_note_id
    def __new__(cls, *args, **kwargs):
        return super().__new__(
            cls,
            entity_id=kwargs["note_id"],
            session=kwargs["session"],
            model_backing=kwargs["model_backing"],
        )

    @require_session
    @require_model
    @require_note_id
    def __init__(
        self,
        title: str = "new note",
        note_type: str = "text",
        mime: str = "text/html",
        parents: Iterable[Note | Branch] | Note | Branch | None = None,
        children: Iterable[Note | Branch] | None = None,
        attributes: Iterable[Attribute] | None = None,
        content: str | bytes | IO | None = None,
        note_id: str | None = None,
        template: Note | type[Note] | None = None,
        session: Session | None = None,
        **kwargs,
    ):
        """
        :param title: Note title
        :param note_type: Note type, one of: `"text"`{l=python}, `"code"`{l=python}, `"file"`{l=python}, `"image"`{l=python}, `"search"`{l=python}, `"book"`{l=python}, `"relationMap"`{l=python}, `"render"`{l=python}
        :param mime: MIME type, needs to be specified only for note types `"code"`{l=python}, `"file"`{l=python}, `"image"`{l=python}
        :param parents: Parent note/branch, or iterable of notes/branches (internally modeled as a `set`{l=python})
        :param children: Iterable of child notes/branches (internally modeled as a `list`{l=python})
        :param attributes: Iterable of attributes (internally modeled as a `list`{l=python})
        :param content: Text/binary content or file handle
        :param note_id: `noteId` to use, will create if it doesn't exist
        :param template: Note to set as target of `~template` relation
        :param session: Session, or `None`{l=python} to use default
        """

        model_backing = kwargs.pop("model_backing")
        child_id_seed = kwargs.pop(
            "child_id_seed", None
        )  # TODO: cleanup, unused
        force_leaf = kwargs.pop("force_leaf", None)

        if kwargs:
            logging.warning(f"Unexpected kwargs: {kwargs}")

        # normalize args
        parents_iter: Iterable[Note | Branch] | None = None
        if parents is not None:
            parents_iter = cast(
                Iterable[Note | Branch], normalize_entities(parents)
            )

        init_done = self._init_done

        # invoke Entity init
        super().__init__(
            entity_id=note_id,
            session=session,
            model_backing=model_backing,
        )

        if init_done:
            assert self.note_id == note_id
            return

        # invoke Mixin init
        Mixin.__init__(self, child_id_seed)

        # get from parent, if True
        if force_leaf:
            self._force_leaf = force_leaf

        # map of fields to potentially update
        fields_update = {
            "title": title,
            "note_type": note_type,
            "mime": mime,
            "attributes": attributes,
            "parents": parents_iter,
            "children": children,
            "content": content,
        }

        # invoke declarative init, getting fields from subclass
        self._invoke_init_decl(fields_update)

        # set content last as note type/mime are required to determine
        # expected content type (text or binary)
        content = cast(str | bytes | IO | None, fields_update.pop("content"))

        # set new fields
        self._set_attrs(**fields_update)

        # check if user didn't override and content is provided by class
        if content is None and self.content_file:
            content = self._get_content_fh()

        self._set_attrs(content=content)

        # assign template if provided
        if template is not None:
            template_obj: Note
            template_cls: type[Note] = get_cls(template)

            if type(template) is NoteMeta:
                # have class

                assert (
                    template_cls._is_singleton()
                ), "Template target must be singleton class"

                # instantiate target
                template_obj = template_cls(session=session)
            else:
                # have instance
                template_obj = cast(Note, template)

            assert isinstance(
                template_obj, Note
            ), f"Template target must be a Note, have {type(template_obj)}"
            self += Relation("template", template_obj, session=session)

    @property
    def _str_short(self):
        return f"Note(title={self.title}, note_id={self.note_id})"

    @property
    def _str_safe(self):
        return f"Note(note_id={self._entity_id}, id={id(self)})"

    @classmethod
    def _from_id(cls, note_id: str, session: Session | None = None):
        return Note(note_id=note_id, session=session)

    @classmethod
    def _from_model(cls, model: EtapiNoteModel, session: Session | None = None):
        return Note(note_id=model.note_id, model_backing=model, session=session)

    def __iadd__(
        self,
        entity: Note
        | tuple[Note, str]
        | Branch
        | Attribute
        | Iterable[Note | tuple[Note, str] | Branch | Attribute],
    ) -> Note:
        """
        Implement entity bind operator:

        note += child_note
        note += (child_note, "prefix")
        note += Branch(parent=parent_note)
        note += Branch(child=child_note)
        note += Label(...)/Relation(...)

        or iterable of any combination.
        """

        entities = normalize_entities(entity)

        for ent in entities:
            if isinstance(ent, Attribute):
                self.attributes.owned.append(ent)
            elif isinstance(ent, Note) or type(ent) is tuple:
                # add child note
                self.branches.children.append(ent)
            else:
                assert isinstance(
                    ent, Branch
                ), f"Unknown type for +=: {type(ent)}"
                branch = ent

                if branch.parent in {None, self}:
                    # note += Branch()
                    # note += Branch(child=child)
                    # note += Branch(parent=note, child=child)
                    self.branches.children.append(branch)
                else:
                    # note += Branch(parent=parent)
                    self.branches.parents.add(branch)

        return self

    def __ixor__(
        self,
        parent: Note | tuple[Note, str] | Iterable[Note | tuple[Note, str]],
    ) -> Note:
        """
        Implement clone operator:

        child ^= parent_note
        child ^= (parent_note, "prefix")
        child ^= [parent1, parent2]
        """

        # iterate and add individually for repeatability
        for p in normalize_entities(parent):
            self.branches.parents.add(p)

        return self

    def __getitem__(self, key: str) -> str | Note:
        """
        Return value of first attribute with provided name.

        :raises KeyError: No such attribute
        """
        attr = self.attributes[key][0]
        if isinstance(attr, Relation):
            return attr.target
        return attr.value

    def __setitem__(self, key: str, value_spec: ValueSpec):
        """
        Create or update attribute with provided name.

        :param key: Attribute name
        :param value_spec: Attribute value
        """
        self.attributes[key] = value_spec

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other

    def __delitem__(self, key: str):
        """
        Delete owned attributes with provided name.

        :param key: Attribute name
        :raises KeyError: No such attribute
        """
        del self.attributes.owned[key]

    def __iter__(self) -> Iterator:
        """
        Iterate over owned and inherited attribute names.

        :return: Iterator over attributes
        """
        yield from self.attributes._name_map

    def __len__(self) -> int:
        """
        Number of owned and inherited attributes.
        """
        return len(self.attributes._name_map)

    def __bool__(self) -> bool:
        """
        Ensure reliable check for truthiness since otherwise it will default
        to going by len(), meaning a note with no attributes would evaluate to
        False.
        """
        return True

    def export_zip(
        self,
        dest_path: str,
        export_format: Literal["html", "markdown"] = "html",
    ):
        """
        Export this note subtree to zip file.

        :param dest_path: Destination .zip file
        :param export_format: Format of exported HTML notes
        """
        self._session.export_zip(self, dest_path, export_format=export_format)

    def import_zip(
        self,
        src_path: str,
    ):
        """
        Import this note subtree from zip file.

        :param src_path: Source .zip file
        """
        self._session.import_zip(self, src_path)

    def flush(self):
        """
        Flush note along with its owned attributes.
        """

        # collect set of entities
        flush_set = {attr for attr in self.attributes.owned}
        flush_set.add(self)  # type: ignore

        self._session.flush(flush_set)

    def _init(self):
        """
        Perform additional init prior to model setup.
        """

        # create extensions
        self._attributes = Attributes(self)
        self._branches = Branches(self)
        self._parents = Parents(self)
        self._children = Children(self)
        self._content = Content(self)

    def _invoke_init_decl(self, fields_update: dict[str, Any]):
        """
        Get fields from subclassed Note.
        """

        # check if note is subclassed
        if self._is_declarative:
            # get fields populated in class
            for field in cast(Iterable[str], NoteModel.fields_update_alias):
                self._get_decl_field(fields_update, field)

            # invoke init chain defined on mixin
            attributes: list[Attribute]
            children: list[BranchSpecT]
            attributes, children = self._init_mixin(fields_update)

            # add originalFilename label if content set from file
            if self.content_file:
                attributes += [
                    self.create_declarative_label(
                        "originalFilename",
                        value=os.path.basename(self.content_file),
                    )
                ]

            # add #cssClass for internal (non-leaf) singleton declarative
            # notes which aren't templates. this enables hiding
            # "create child" button (templates should always be modifiable
            # since the cssClass would be inherited to instances created
            # by user)
            if self.note_id:
                if (
                    self.hide_new_note
                    or any([self.leaf, self._force_leaf]) is False
                ):
                    attributes += [
                        self.create_declarative_label(
                            "cssClass", value="triliumAlchemyDeclarative"
                        )
                    ]

            if fields_update["attributes"] is not None:
                fields_update["attributes"] += attributes
            else:
                fields_update["attributes"] = attributes

            if self.leaf:
                # leaf note: make sure there are no declarative children
                # - leaf note means the user manually maintains children in UI
                # or syncs from a folder
                assert (
                    len(children) == 0
                ), f"Attempt to declaratively update children of leaf note {self}"
            else:
                # not a leaf note: free to update children
                if fields_update["children"] is not None:
                    # prepend provided children
                    children = fields_update["children"] + children

                # instantiate any classes provided, either through
                # @children decorator or constructor
                fields_update["children"] = self._normalize_children(children)

    @property
    def is_string(self) -> bool:
        """
        `True`{l=python} if note as it's currently configured has text content.

        Mirrors Trilium's `src/services/utils.js:isStringNote()`.
        """
        return is_string(self.note_type, self.mime)

    @property
    def _is_declarative(self) -> bool:
        return type(self) is not Note

    @classmethod
    def _get_decl_id(cls, parent: Mixin | None = None) -> str | None:
        """
        Try to get a note_id. If one is returned, this note has a deterministic
        note_id and will get the same one every time it's instantiated.
        """

        module: ModuleType | None = inspect.getmodule(cls)
        assert module is not None

        # get fully qualified class name
        cls_name = f"{module.__name__}.{cls.__name__}"

        if hasattr(cls, "note_id_"):
            # note_id provided and renamed by metaclass
            return getattr(cls, "note_id_")
        elif cls.note_id_seed:
            # note_id_seed provided
            return id_hash(getattr(cls, "note_id_seed"))
        elif cls.idempotent:
            # get id from class name (not fully-qualified)
            return id_hash(cls.__name__)
        elif cls.singleton:
            # get id from fully-qualified class name
            return id_hash(cls_name)
        elif parent is not None:
            # not declared as singleton, but possibly created by
            # singleton parent, so try to generate deterministic id

            # select base as provided segment or fully-qualified class name
            base: str = cls.note_id_segment or cls_name

            return parent._derive_id(Note, base)

        return None

    @classmethod
    def _is_singleton(cls) -> bool:
        return cls._get_decl_id() is not None

    def _flush_check(self):
        if not self._is_delete:
            _assert_validate(
                len(self.branches.parents) > 0, "Note has no parents"
            )

        for branch in self.branches.parents:
            _assert_validate(
                branch.child is self,
                f"Child not set for parent branch {branch}",
            )

            if self.note_id != "root":
                _assert_validate(
                    branch.parent is not None,
                    f"Parent not set for branch: {branch}",
                )

        for branch in self.branches.children:
            _assert_validate(branch.parent is self)

    @property
    def _dependencies(self):
        deps = set()

        if self.note_id != "root":
            # parent notes
            deps |= {branch.parent for branch in self.branches.parents}

        return deps

    def _get_decl_field(self, fields_update: dict[str, Any], field: str):
        if fields_update[field] is None:
            # need unique name to preserve access to model field using
            # getattr/setattr
            attr = field + "_"

            if hasattr(self, attr):
                # field explicitly provided by subclass
                fields_update[field] = getattr(self, attr)
            else:
                if field == "title":
                    # get title from class name
                    fields_update["title"] = type(self).__name__
                else:
                    # get default field
                    fields_update[field] = self._model._field_default(field)

    # Return handle of file specified by content_file
    def _get_content_fh(self) -> IO:
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

            with importlib.resources.path(module_content, basename) as path:
                content_path = str(path)
        except ModuleNotFoundError as e:
            # not in a package context (e.g. test code, standalone script)
            path_folder = os.path.dirname(str(module.__file__))
            content_path = os.path.join(path_folder, self.content_file)

        assert os.path.isfile(
            content_path
        ), f"Content file specified by {cls} does not exist: {content_path}"

        mode = "r" if self.is_string else "rb"
        return open(content_path, mode)
