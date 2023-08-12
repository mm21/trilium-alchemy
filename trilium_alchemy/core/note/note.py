from __future__ import annotations

from typing import overload, TypeVar, Generic, Type, Hashable, Any, IO, Literal
from collections.abc import Iterable
from graphlib import TopologicalSorter
from abc import ABC, ABCMeta
from functools import wraps, partial
import importlib.resources
import hashlib
import base64
import inspect
import os
import logging

from trilium_client.models.note import Note as EtapiNoteModel
from trilium_client.models.attribute import Attribute as EtapiAttributeModel
from trilium_client.models.create_note_def import CreateNoteDef
from trilium_client.models.note_with_branch import NoteWithBranch
from trilium_client.exceptions import NotFoundException

from ..exceptions import *
from ..session import Session, require_session
from ..entity.entity import (
    Entity,
    EntityIdDescriptor,
)
from ..entity.model import (
    Model,
    FieldDescriptor,
    ReadOnlyFieldDescriptor,
    ExtensionDescriptor,
    require_model,
)

from ..attribute import Attribute, Label, Relation
from ..branch import Branch

from .attributes import Attributes, ValueSpec
from .branches import (
    Parents,
    Children,
    Branches,
)
from .content import Content, ContentDescriptor

import trilium_alchemy

__all__ = [
    "Note",
    "Mixin",
]


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


class Meta(ABCMeta):
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

        note_cls = super().__new__(cls, name, bases, attrs)
        cls_init = note_cls.__init__

        # wrap __init__ to take defaults as None. this is needed to
        # avoid clobbering title/type/mime for existing notes, but still
        # document the defaults for new note creation in the API
        @wraps(cls_init)
        def __init__(self, **kwargs):
            for field in NoteModel.fields_update_alias:
                if field not in kwargs:
                    kwargs[field] = None

            cls_init(self, **kwargs)

        note_cls.__init__ = __init__

        return note_cls


class Mixin(ABC, metaclass=Meta):
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

    note_id: str = None
    """
    `note_id` to explicitly assign.
    """

    note_id_seed: str = None
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

    title: str = None
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
    `note_id` which will break any non-declarative relations to it. To avoid 
    changing the `note_id` you can set `note_id_seed` to the original fully 
    qualified class name.
    ```
    """

    leaf = False
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

    content_file: str = None
    """
    Name of file to use as content, relative to module's location. Also adds 
    `#originalFilename` label.

    ```{note}
    Currently Trilium only shows `#originalFilename` if the note's type is
    `file`.
    ```
    """

    _force_leaf = False
    """
    If we applied the triliumAlchemyDeclarative CSS class to templates and
    their children, the user wouldn't be able to modify children of instances
    of that template in the UI since the cssClass would be inherited as well.

    This is a simple way to work around that by forcing this note to act as
    a leaf note for the purpose of checking whether to add the cssClass, 
    even though we still want to maintain the template itself declaratively.
    """

    # Raise exception if instantiated directly
    def __init__(self):
        raise Exception(
            "Not allowed to instantiate Mixin: subclass in Note instead"
        )

    def init(
        self, attributes: list[Attribute], children: list[Branch | Note]
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
        self, child_cls: Type[Note], **kwargs
    ) -> Branch:
        """
        Create a child {obj}`Note` with deterministic `note_id` and return a
        {obj}`Branch`. Should be used in subclassed
        {obj}`Note.init` or {obj}`Mixin.init` to generate
        the same child `note_id` upon every instantiation.

        Instantiate provided class as a declarative child of the current
        note by generating a deterministic id and returning the
        corresponding branch.
        """
        child_note_id = child_cls._get_decl_id(self)

        child = child_cls(
            note_id=child_note_id,
            session=self._session,
            force_leaf=self._force_leaf,
            **kwargs,
        )

        # check if ids are known
        if self.note_id is not None:
            # if ids are known at this point, also generate branch id
            branch_id = Branch._gen_branch_id(self, child)
        else:
            branch_id = None

        return Branch(
            parent=self, child=child, branch_id=branch_id, session=self._session
        )

    # Invoke declarative init and return tuple of attributes, children
    def _init_mixin(
        self, fields_update: dict[str, Any]
    ) -> tuple[list[Attribute], list[Branch | Note | Type[Note]]]:
        attributes: list[Attribute] = list()
        children: list[Branch | Note | Type[Note]] = list()

        # traverse MRO to add attributes and children in an intuitive order.
        # for each class in the MRO:
        # - add decorator-based attributes/children
        # - add init()-based attributes/children
        # a nice side effect of this is the user doesn't have to invoke
        # super().init()
        for cls in type(self).mro():
            if issubclass(cls, Mixin):
                # invoke init chain added by decorators
                cls._init_decl(
                    self, cls, attributes=attributes, children=children
                )

                # invoke manually implemented init()
                if not is_inherited(cls, "init"):
                    fields = cls.init(self, attributes, children)
                    if fields:
                        # TODO: restrict fields which can be updated
                        fields_update.update(fields)

        return attributes, children

    # Base declarative init method which can be patched by decorators
    def _init_decl(self, cls_decl, *, attributes, children):
        pass

    # Return class which specified content_file
    def _get_content_cls(self):
        for cls in type(self).mro():
            if issubclass(cls, Mixin) and cls.content_file:
                return cls

    # Return handle of file specified by content_file
    def _get_content_fh(self):
        # get class which defined content_file
        cls = self._get_content_cls()
        assert cls is not None

        # get path to content from class

        module = inspect.getmodule(cls)

        content_path: str = None

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
                content_path = path
        except ModuleNotFoundError as e:
            # not in a package context (e.g. test code, standalone script)
            path_folder = os.path.dirname(module.__file__)
            content_path = os.path.join(path_folder, self.content_file)

        assert os.path.isfile(
            content_path
        ), f"Content file specified by {cls} does not exist: {content_path}"

        mode = "r" if self.is_string else "rb"
        return open(content_path, mode)


def patch_init(init, doc: str = None):
    """
    Insert provided init function in class's declarative init sequence.
    """

    def _patch_init(cls):
        init_decl_old = cls._init_decl

        @wraps(init_decl_old)
        def _init_decl(self, cls_decl, *, attributes, children):
            if cls is cls_decl:
                # invoke init patch
                init(self, attributes=attributes, children=children)

                # invoke old init
                init_decl_old(
                    self, cls_decl, attributes=attributes, children=children
                )

        cls._init_decl = _init_decl

        if doc:
            # append to docstring
            cls._decorator_doc.append(doc)

        return cls

    return _patch_init


"""
TODO: have list of valid types, validate using custom descriptor
for note_type
class NoteType(StrEnum):
    text = auto()
    code = auto()
    render = auto()
    file = auto()
    image = auto()
    search = auto()
    relationMap = auto()
    book = auto()
    noteMap = auto()
    mermaid = auto()
    webView = auto()
    shortcut = auto()
    doc = auto()
    contentWidget = auto()
    launcher = auto()
"""


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


def get_cls(ent: Note | Type[Note]) -> Type[Note]:
    """
    Check if note is a class or instance and return the class.
    """
    if type(ent) is Meta:
        # have class
        return ent
    else:
        # have instance
        return type(ent)


def is_inherited(cls: Type[Mixin], attr: str) -> bool:
    """
    Check if given attribute is inherited from superclass (True) or defined on this
    class (False).
    """
    value = getattr(cls, attr)
    return any(
        value is getattr(cls_super, attr, object())
        for cls_super in cls.__bases__
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


class NoteModel(Model):
    etapi_model = EtapiNoteModel
    field_entity_id = "note_id"

    fields_alias = {
        "note_type": "type",
    }

    fields_update = [
        "title",
        "type",
        "mime",
    ]

    # this is where the actual defaults come from; defaults in
    # Note.__init__ are only for documentation
    fields_default = {
        "title": "new note",
        "type": "text",
        "mime": "text/html",
    }


class Note(Entity[NoteModel], Mixin, metaclass=Meta):
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

    note_id: str | None = EntityIdDescriptor()
    """
    Read-only access to `noteId`. Will be `None`{l=python} if
    newly created with no `note_id` specified and not yet flushed.
    """

    title: str = FieldDescriptor("title")
    """
    Note title.
    """

    # TODO: custom descriptor for type w/validation
    note_type: str = FieldDescriptor("type")
    """
    Note type.
    """

    mime: str = FieldDescriptor("mime")
    """
    MIME type.
    """

    is_protected: bool = ReadOnlyFieldDescriptor("is_protected")
    """
    Whether this note is protected.
    """

    date_created: str = ReadOnlyFieldDescriptor("date_created")
    """
    Local created datetime, e.g. `2021-12-31 20:18:11.939+0100`.
    """

    date_modified: str = ReadOnlyFieldDescriptor("date_modified")
    """
    Local modified datetime, e.g. `2021-12-31 20:18:11.939+0100`.
    """

    utc_date_created: str = ReadOnlyFieldDescriptor("utc_date_created")
    """
    UTC created datetime, e.g. `2021-12-31 19:18:11.939Z`.
    """

    utc_date_modified: str = ReadOnlyFieldDescriptor("utc_date_modified")
    """
    UTC modified datetime, e.g. `2021-12-31 19:18:11.939Z`.
    """

    attributes: Attributes = ExtensionDescriptor("_attributes")
    """
    Interface to attributes, both owned and inherited.
    """

    branches: Branches = ExtensionDescriptor("_branches")
    """
    Interface to branches, both parent and child.
    """

    parents: Parents = ExtensionDescriptor("_parents")
    """
    Interface to parent notes.
    """

    children: Children = ExtensionDescriptor("_children")
    """
    Interface to child notes.
    """

    content: str | bytes = ContentDescriptor("_content")
    """
    Interface to note content. See {obj}`trilium_alchemy.core.note.content.Content`.
    """

    _model_cls = NoteModel

    # model extensions
    _attributes: Attributes = None
    _branches: Branches = None
    _parents: Parents = None
    _children: Children = None
    _content: Content = None

    # state to keep track of sequence numbers for deterministic attribute/
    # child ids
    _sequence_map: dict[type, dict[str, int]] = None

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
        parents: set[Note | Branch] | Note | Branch = None,
        children: list[Note | Branch] = None,
        attributes: list[Attribute] = None,
        content: str | bytes | IO = None,
        note_id: str = None,
        template: Note | Type[Note] = None,
        session: Session = None,
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
        child_id_seed = kwargs.pop("child_id_seed", None)
        force_leaf = kwargs.pop("force_leaf", None)

        if kwargs:
            logging.warning(f"Unexpected kwargs: {kwargs}")

        # normalize args
        if parents and not isinstance(parents, Iterable):
            parents = {parents}

        init_done = self._init_done

        # invoke base init
        super().__init__(
            entity_id=note_id,
            session=session,
            model_backing=model_backing,
        )

        if init_done:
            assert self.note_id == note_id
            return

        self._sequence_map = dict()
        self._child_id_seed = child_id_seed

        # get from parent, if True
        if force_leaf:
            self._force_leaf = force_leaf

        # map of fields to potentially update
        fields_update = {
            "title": title,
            "note_type": note_type,
            "mime": mime,
            "attributes": attributes,
            "parents": parents,
            "children": children,
            "content": content,
        }

        # invoke declarative init, getting fields from subclass
        self._invoke_init_decl(fields_update)

        # set content last as note type/mime are required to determine
        # expected content type (text or binary)
        content = fields_update.pop("content")

        # set new fields
        self._set_attrs(**fields_update)

        # check if user didn't override and content is provided by class
        if content is None and self.content_file:
            content = self._get_content_fh()

        self._set_attrs(content=content)

        # assign template if provided
        if template:
            if type(template) is Meta:
                assert (
                    template._is_singleton
                ), "Template target must be singleton class"
                template = template(session=session)
            assert isinstance(
                template, Note
            ), f"Template target must be a Note, have {type(template)}"
            self += Relation("template", template, session=session)

    @property
    def _str_short(self):
        return f"Note(title={self.title}, note_id={self.note_id})"

    @property
    def _str_safe(self):
        return f"Note(note_id={self._entity_id}, id={id(self)})"

    @classmethod
    def _from_id(self, note_id: str, session: Session = None):
        return Note(note_id=note_id, session=session)

    @classmethod
    def _from_model(self, model: EtapiNoteModel, session: Session = None):
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

        entities = (
            entity
            if isinstance(entity, Iterable) and not isinstance(entity, tuple)
            else [entity]
        )

        for entity in entities:
            if isinstance(entity, Attribute):
                self.attributes.owned.append(entity)
            elif isinstance(entity, Note) or type(entity) is tuple:
                # add child note
                self.branches.children.append(entity)
            else:
                assert isinstance(
                    entity, Branch
                ), f"Unknown type for +=: {type(entity)}"
                branch = entity

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
        parents = (
            {p for p in parent}
            if isinstance(parent, Iterable) and not type(parent) is tuple
            else {parent}
        )

        self.branches.parents |= parents

        return self

    def __getitem__(self, key: str | int) -> str | Note:
        """
        Return value of first attribute with provided name.

        :raises KeyError: No such attribute
        """

        # get list of attributes with name
        attrs = self.attributes[key]

        if len(attrs):
            attr = attrs[0]

            if isinstance(attr, Relation):
                return attr.target
            else:
                return attr.value

    def __setitem__(self, key: str | int, value_spec: ValueSpec):
        """
        Create or update attribute with provided name.
        """
        self.attributes[key] = value_spec

    def __contains__(self, key: str) -> bool:
        return key in self.attributes._name_map

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

    def flush(self, **kwargs):
        """
        Flush note along with its attributes.

        ```{todo}
        Remove `recursive` kwarg. It will cache the entire subtree which is
        likely unexpected; use {obj}`Session.flush` instead.
        ```
        """

        if recursive := kwargs.pop("recursive", None) is not None:
            logging.warning(
                "Note.flush() arg recursive is deprecated and will be removed in a future release. It will cache the entire subtree which is likely unexpected; use Session.flush() instead."
            )

        if kwargs:
            logging.warning(f"Unexpected kwargs: {kwargs}")

        # collect set of entities to flush
        flush_set = set()
        self._flush_gather(flush_set, recursive=recursive)

        # flush note (and subtree if recursive)
        self._session.flush(flush_set)

    def _flush_gather(self, flush_set: set[Entity], recursive=False):
        """
        Collect and return entities to be flushed.
        """

        flush_set.add(self)

        # attributes
        flush_set |= {attr for attr in self.attributes.owned}

        # branches
        flush_set |= {branch for branch in self.branches}

        if recursive:
            for child in self.children:
                child._flush_gather(flush_set, recursive=recursive)

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
            for field in NoteModel.fields_update_alias:
                self._get_decl_field(fields_update, field)

            # invoke init chain defined on mixin
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
                if not self.leaf and not self._force_leaf:
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
                    fields_update["children"] += children
                else:
                    fields_update["children"] = children

            # instantiate any classes provided, either through
            # @children decorator or constructor
            if fields_update["children"] is not None:
                for index, child_spec in enumerate(fields_update["children"]):
                    # extract branch args if provided
                    if type(child_spec) is tuple:
                        child_cls, branch_kwargs = child_spec
                    else:
                        child_cls = child_spec
                        branch_kwargs = dict()

                    if type(child_cls) is Meta:
                        branch = self.create_declarative_child(child_cls)

                        # set branch kwargs
                        for key, value in branch_kwargs.items():
                            setattr(branch, key, value)

                        fields_update["children"][index] = branch

    @property
    def is_string(self) -> bool:
        """
        `True`{l=python} if note as it's currently configured has text content.

        Mirrors Trilium's `src/services/utils.js:isStringNote()`.
        """
        return is_string(self.note_type, self.mime)

    @property
    def _is_declarative(self):
        return type(self) is not Note

    @classmethod
    def _get_decl_id(cls, parent: Note = None):
        """
        Try to get a note_id. If one is returned, this note has a deterministic
        note_id and will get the same one every time it's instantiated.
        """

        # get fully qualified class name
        cls_name = f"{inspect.getmodule(cls).__name__}.{cls.__name__}"

        if hasattr(cls, "note_id_"):
            # note_id provided and renamed by metaclass
            return getattr(cls, "note_id_")
        elif cls.note_id_seed:
            # note_id_seed provided
            return id_hash(getattr(cls, "note_id_seed"))
        elif cls.singleton:
            # get id from class name
            return id_hash(cls_name)
        elif parent:
            # not declared as singleton, but possibly created by
            # singleton parent, so try to generate deterministic id
            return parent._derive_id(Note, cls_name)

    @property
    @classmethod
    def _is_singleton(cls) -> bool:
        return cls._get_decl_id() is not None

    def _flush_check(self):
        if not self._is_delete:
            assert len(self.branches.parents) > 0, "Note has no parents"

        for branch in self.branches.parents:
            assert (
                branch.child is self
            ), f"Child not set for parent branch {branch}"

            if self.note_id != "root":
                assert (
                    branch.parent is not None
                ), f"Parent not set for branch: {branch}"

        for branch in self.branches.children:
            assert branch.parent is self

    def _flush_create(self, sorter: TopologicalSorter) -> EtapiNoteModel:
        # pick first parent branch according to serialization provided by
        # ParentBranches
        parent_branch = self.branches.parents[0]

        # ensure parent note exists (should be taken care by sorter)
        assert parent_branch.parent._model.exists

        # get note fields
        model_dict = self._model._working.copy()

        model_dict["parent_note_id"] = parent_branch.parent.note_id

        # for simplicity, always init content as empty string and let
        # content extension set content later (handling text/bin)
        model_dict["content"] = ""

        if self.note_id is not None:
            model_dict["note_id"] = self.note_id

        # assign writeable fields from branch
        for field in parent_branch._model.fields_update:
            model_dict[field] = parent_branch._model.get_field(field)

        model = CreateNoteDef(**model_dict)

        # invoke api
        response: NoteWithBranch = self._session.api.create_note(model)

        # add parent branch to cache before note is loaded
        # (branches will be instantiated)
        if parent_branch.branch_id is None:
            parent_branch._set_entity_id(response.branch.branch_id)
        else:
            assert parent_branch.branch_id == response.branch.branch_id

        # mark parent as clean
        parent_branch._set_clean()

        # if parent was added to sorter, mark it as done
        # (it may not have been part of sorter, even though it's dirty if e.g.
        # the user called .flush() directly)
        try:
            sorter.done(parent_branch)
        except ValueError as e:
            pass

        # return note model for processing
        yield response.note

        # load parent branch model
        parent_branch._model.setup(response.branch)

    def _flush_update(self, sorter: TopologicalSorter) -> EtapiNoteModel:
        # assemble note model based on needed fields
        model = EtapiNoteModel(**self._model.get_fields_changed())

        # invoke api and return new model
        model_new: EtapiNoteModel = self._session.api.patch_note_by_id(
            self.note_id, model
        )
        assert model_new is not None

        return model_new

    def _flush_delete(self, sorter: TopologicalSorter):
        self._session.api.delete_note_by_id(self.note_id)

        # mark attributes as clean
        for attr in self.attributes.owned:
            if attr._is_dirty:
                attr._set_clean()
                sorter.done(attr)

        # mark child branches as clean
        for branch in self.branches.children:
            if branch._is_dirty:
                branch._set_clean()
                sorter.done(branch)

    def _fetch(self) -> EtapiNoteModel | None:
        model: EtapiNoteModel | None

        try:
            model = self._session.api.get_note_by_id(self.note_id)
        except NotFoundException as e:
            model = None

        return model

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

    def _derive_id(self, cls, base) -> str:
        """
        Generate a declarative entity id unique to this note with namespace
        per class. Increments a sequence number per base, so e.g. there can be
        multiple attributes with the same name.
        """

        if self.note_id:
            # if child_id_seed was passed during init, use that to generate
            # deterministic child ids invariant of the root id.
            # this enables setting a tree of ids based on the app name rather
            # than the root note it's installed to
            if self._child_id_seed:
                prefix = self._child_id_seed
            else:
                prefix = self.note_id

            sequence = self._get_sequence(cls, base)
            return id_hash(f"{prefix}_{base}_{sequence}")
        else:
            return None

    def _get_sequence(self, cls, base):
        if cls not in self._sequence_map:
            self._sequence_map[cls] = dict()

        if base in self._sequence_map[cls]:
            self._sequence_map[cls][base] += 1
        else:
            self._sequence_map[cls][base] = 0

        return self._sequence_map[cls][base]
