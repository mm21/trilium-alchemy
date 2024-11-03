from __future__ import annotations

import base64
import hashlib
from abc import ABCMeta
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass
from typing import IO, Any, Iterator, Literal, Self, cast

from trilium_client.models.note import Note as EtapiNoteModel

from ..attribute import BaseAttribute, Label, Relation
from ..branch import Branch
from ..entity.entity import BaseEntity, EntityIdDescriptor, normalize_entities
from ..entity.model import (
    ExtensionDescriptor,
    FieldDescriptor,
    ReadOnlyFieldDescriptor,
)
from ..exceptions import _assert_validate
from ..session import Session
from .attributes import Attributes, ValueSpec
from .branches import Branches, Children, Parents
from .content import Content, ContentDescriptor
from .model import NoteModel

__all__ = [
    "Note",
]


type BranchSpecT = "Note" | type["Note"] | Branch | tuple[
    "Note" | type["Note"] | Branch, dict[str, Any]
]
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
    if isinstance(ent, ABCMeta):
        # have class
        return cast(type[Note], ent)
    # have instance
    return cast(type[Note], type(ent))


class Note(
    BaseEntity[NoteModel],
    MutableMapping,
):
    """
    Encapsulates a note and provides a base class for declarative notes.

    For a detailed walkthrough of how to use this class, see
    {ref}`Working with notes <working-with-notes-notes>`.
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

    def __new__(cls, *_, **kwargs) -> Self:
        note_id, _ = cls._get_note_id(kwargs.get("note_id"))
        return super().__new__(
            cls,
            entity_id=note_id,
            session=kwargs.get("session"),
            model_backing=kwargs.get("model_backing"),
        )

    def __init__(
        self,
        title: str | None = None,
        note_type: str | None = None,
        mime: str | None = None,
        parents: Iterable[Note | Branch] | Note | Branch | None = None,
        children: Iterable[Note | Branch] | None = None,
        attributes: Iterable[BaseAttribute] | None = None,
        content: str | bytes | IO | None = None,
        note_id: str | None = None,
        template: Note | type[Note] | None = None,
        session: Session | None = None,
        **kwargs,
    ):
        """
        :param title: Note title
        :param note_type: Note type, default `text`; one of: `"text"`{l=python}, `"code"`{l=python}, `"file"`{l=python}, `"image"`{l=python}, `"search"`{l=python}, `"book"`{l=python}, `"relationMap"`{l=python}, `"render"`{l=python}
        :param mime: MIME type, default `text/html`; needs to be specified only for note types `"code"`{l=python}, `"file"`{l=python}, `"image"`{l=python}
        :param parents: Parent note/branch, or iterable of notes/branches (internally modeled as a `set`{l=python})
        :param children: Iterable of child notes/branches (internally modeled as a `list`{l=python})
        :param attributes: Iterable of attributes (internally modeled as a `list`{l=python})
        :param content: Text/binary content or file handle
        :param note_id: `noteId` to use, will create if it doesn't exist
        :param template: Note to set as target of `~template` relation
        :param session: Session, or `None`{l=python} to use default
        :param kwargs: Internal only
        """

        note_id, note_id_seed_final = get_cls(self)._get_note_id(note_id)

        # TODO: prefix internal-only kwargs with "_"
        note_id_seed_final = (
            kwargs.pop("note_id_seed_final", None) or note_id_seed_final
        )
        model_backing = kwargs.pop("model_backing", None)
        force_leaf = kwargs.pop("force_leaf", None)

        assert len(kwargs) == 0, f"Unexpected kwargs: {kwargs}"

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

        all_attributes: list[BaseAttribute] | None = None
        all_children: list[Note] | None = None

        if attributes is not None:
            all_attributes = attributes

        if children is not None:
            all_children = children

        # get container from any subclass
        init_container = self._init_hook(
            note_id, note_id_seed_final, force_leaf
        )

        if init_container.attributes is not None:
            if all_attributes is None:
                all_attributes = init_container.attributes
            else:
                all_attributes += init_container.attributes

        if init_container.children is not None:
            if all_children is None:
                all_children = init_container.children
            else:
                all_children += init_container.children

        # assign template if provided
        if template is not None:
            template_obj: Note
            template_cls: type[Note] = get_cls(template)

            if isinstance(template, ABCMeta):
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

            relation = Relation("template", template_obj, session=session)

            if all_attributes is None:
                all_attributes = [relation]
            else:
                all_attributes.append(relation)

        if (title_set := title or init_container.title) is not None:
            self.title = title_set

        if (note_type_set := note_type or init_container.note_type) is not None:
            self.note_type = note_type_set

        if (mime_set := mime or init_container.mime) is not None:
            self.mime = mime_set

        # set after type/mime to determine expected content type
        # (text or binary)
        if (content_set := content or init_container.content) is not None:
            self.content = content_set

        if all_attributes is not None:
            self.attributes = all_attributes

        if all_children is not None:
            self.children = all_children

        if parents_iter is not None:
            self.parents = parents_iter

    def __iadd__(
        self,
        entity: Note
        | tuple[Note, str]
        | Branch
        | BaseAttribute
        | Iterable[Note | tuple[Note, str] | Branch | BaseAttribute],
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
            if isinstance(ent, BaseAttribute):
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

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other) -> bool:
        return self is other

    def __delitem__(self, key: str):
        """
        Delete owned attributes with provided name.

        :param key: Attribute name
        :raises KeyError: No such attribute
        """
        del self.attributes.owned[key]

    def __iter__(self) -> Iterator[str]:
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

    @property
    def is_string(self) -> bool:
        """
        `True`{l=python} if note as it's currently configured has text content.

        Mirrors Trilium's `src/services/utils.js:isStringNote()`.
        """
        return is_string(self.note_type, self.mime)

    @property
    def paths(self) -> list[list[Note]]:
        """
        Get list of paths to this note, where each path is a list of
        ancestor notes.
        """

        def get_paths(note: Note) -> list[list[Note]]:
            paths: list[list[Note]] = []

            # get list of parents sorted by title
            parents: list[Note] = sorted(note.parents, key=lambda n: n.title)

            # if no parents, just add this note
            if len(parents) == 0:
                paths.append([note])

            # traverse parents
            for parent in parents:
                for path in get_paths(parent):
                    paths.append(path + [note])

            return paths

        return get_paths(self)

    @property
    def paths_str(self) -> list[str]:
        """
        Get list of paths to this note, where each path is a string
        like `A > B > C`.
        """
        return [
            " > ".join([note.title for note in path]) for path in self.paths
        ]

    def copy(self, deep: bool = False, content: bool = False) -> Note:
        """
        Return a copy of this note, including its title, type, MIME,
        attributes, and optionally content.

        If `deep` is `False`{l=python}, child notes are cloned to the
        returned copy. Otherwise, child notes are recursively deep copied.

        ```{note}
        The returned copy still needs to be placed in the tree hierarchy
        (added as a child of another note) before `Session.flush()`
        is invoked.
        ```
        """

        # create note
        note_copy = Note(
            title=self.title,
            note_type=self.note_type,
            mime=self.mime,
            session=self.session,
        )

        # copy content if indicated
        if content:
            note_copy.content = self.content

        # copy attributes
        for attr in self.attributes.owned:
            assert isinstance(attr, Label) or isinstance(attr, Relation)

            if isinstance(attr, Label):
                note_copy += Label(
                    attr.name,
                    value=attr.value,
                    inheritable=attr.inheritable,
                    session=self.session,
                )
            else:
                note_copy += Relation(
                    attr.name,
                    attr.target,
                    inheritable=attr.inheritable,
                    session=self.session,
                )

        # copy children
        for branch in self.branches.children:
            # copy or clone this child
            child = (
                branch.child.copy(deep=deep, content=content)
                if deep
                else branch.child
            )

            # create new branch with same prefix
            note_copy += Branch(
                child=child,
                prefix=branch.prefix,
                session=self.session,
            )

        return note_copy

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

    def _init_hook(
        self,
        note_id: str | None,
        note_id_seed_final: str | None,
        force_leaf: bool | None,
    ) -> InitContainer:
        """
        Override to perform additional init for subclasses.
        """
        return InitContainer()

    @property
    def _dependencies(self):
        deps = set()

        if self.note_id != "root":
            # parent notes
            deps |= {branch.parent for branch in self.branches.parents}

        return deps

    @property
    def _str_short(self):
        return f"Note(title={self.title}, note_id={self.note_id})"

    @property
    def _str_safe(self):
        return f"Note(note_id={self._entity_id}, id={id(self)})"

    @classmethod
    def _get_note_id(cls, note_id: str | None) -> tuple[str | None, str | None]:
        return (note_id, None)

    @classmethod
    def _is_singleton(cls) -> bool:
        return False

    @classmethod
    def _from_id(cls, note_id: str, session: Session | None = None):
        return Note(note_id=note_id, session=session)

    @classmethod
    def _from_model(cls, model: EtapiNoteModel, session: Session | None = None):
        return Note(note_id=model.note_id, session=session, model_backing=model)

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


@dataclass
class InitContainer:
    title: str | None = None
    note_type: str | None = None
    mime: str | None = None
    attributes: list[BaseAttribute] | None = None
    children: list[Note] | None = None
    content: str | bytes | IO | None = None
