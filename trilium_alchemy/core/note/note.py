from __future__ import annotations

import base64
import hashlib
from abc import ABCMeta
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Literal, Self, cast

import requests
from trilium_client.models.note import Note as EtapiNoteModel
from trilium_client.models.note_with_branch import NoteWithBranch

from ..attribute import BaseAttribute, Label, Relation
from ..branch import Branch
from ..entity.entity import BaseEntity, normalize_entities
from ..entity.model import require_setup_prop
from ..exceptions import _assert_validate
from ..session import Session
from .attributes.attributes import Attributes
from .attributes.labels import Labels
from .attributes.relations import Relations
from .branches import Branches, ChildNotes, ParentNotes
from .content import Content
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

STRING_NOTE_TYPES = [
    "text",
    "code",
    "relationMap",
    "search",
    "render",
    "book",
    "mermaid",
    "canvas",
]
"""
Keep in sync with isStringNote() (src/services/utils.js).
"""

NOTE_TYPES = STRING_NOTE_TYPES + [
    "file",
    "image",
]

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


class Note(BaseEntity[NoteModel]):
    """
    Encapsulates a note. Can be subclassed for custom attribute accessors.

    For a detailed walkthrough of how to use this class, see
    {ref}`Working with notes <working-with-notes-notes>`.
    """

    _model_cls = NoteModel

    # model extensions
    _attributes: Attributes
    _branches: Branches
    _parents: ParentNotes
    _children: ChildNotes
    _content: Content

    # stateless accessors
    _labels: Labels
    _relations: Relations

    def __new__(cls, *_, **kwargs) -> Self:
        note_id, _ = cls._get_note_id(kwargs.get("note_id"))
        return super().__new__(
            cls,
            session=kwargs.get("session"),
            entity_id=note_id,
            model_backing=kwargs.get("_model_backing"),
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

        note_id_seed_final = (
            kwargs.pop("_note_id_seed_final", None) or note_id_seed_final
        )
        model_backing = kwargs.pop("_model_backing", None)
        force_leaf = kwargs.pop("_force_leaf", None)

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

        def combine_lists[T](*lists: list[T] | None) -> list[T] | None:
            result: list[T] | None = None

            for lst in lists:
                if lst is not None:
                    if result is None:
                        result = []

                    result += lst

            return result

        # get container from any subclass
        init_container = self._init_hook(
            note_id, note_id_seed_final, force_leaf
        )

        all_attributes = combine_lists(attributes, init_container.attributes)
        all_children = combine_lists(children, init_container.children)

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

        # iterate and add as parent
        for p in normalize_entities(parent):
            self.branches.parents.add(p)

        return self

    def __getitem__(self, name: str) -> str:
        """
        Return value of first attribute with provided name.

        :raises KeyError: No such attribute
        """
        assert isinstance(
            name, str
        ), f"Invalid type for label name: {name} ({type(name)})"

        attr = self.labels.owned.get(name)

        if attr is None:
            raise KeyError(f"Attribute does not exist: {name}, note {self}")

        return attr.value

    def __setitem__(self, name: str, value: str):
        """
        Create or update owned label with provided name.

        :param name: Label name
        :param val: Label value
        """
        assert isinstance(
            name, str
        ), f"Invalid type for label name: {name} ({type(name)})"
        assert isinstance(
            value, str
        ), f"Invalid type for label value: {value} ({type(value)})"
        self.labels.owned.set_value(name, value)

    def __contains__(self, label: str):
        return self.labels.owned.get(label) is not None

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other) -> bool:
        return self is other

    @property
    def note_id(self) -> str | None:
        """
        Getter for `noteId`, or `None` if not created yet.
        """
        return self._entity_id

    @property
    def title(self) -> str:
        """
        Getter/setter for note title.
        """
        return self._model.get_field("title")

    @title.setter
    def title(self, val: str):
        self._model.set_field("title", val)

    @property
    def note_type(self) -> str:
        """
        Getter/setter for note title.
        """
        return self._model.get_field("type")

    @note_type.setter
    def note_type(self, val: str):
        assert val in NOTE_TYPES, f"Invalid note_type: {val}"
        self._model.set_field("type", val)

    @property
    def mime(self) -> str:
        """
        Getter/setter for MIME type.
        """
        return self._model.get_field("mime")

    @mime.setter
    def mime(self, val: str):
        self._model.set_field("mime", val)

    @property
    def is_protected(self) -> bool:
        """
        Protected state, can only be changed in Trilium UI.
        """
        return self._model.get_field("is_protected")

    @property
    def date_created(self) -> str:
        """
        Local created datetime, e.g. `2021-12-31 20:18:11.939+0100`.
        """
        return self._model.get_field("date_created")

    @property
    def date_modified(self) -> str:
        """
        Local modified datetime, e.g. `2021-12-31 20:18:11.939+0100`.
        """
        return self._model.get_field("date_modified")

    @property
    def utc_date_created(self) -> str:
        """
        UTC created datetime, e.g. `2021-12-31 19:18:11.939Z`.
        """
        return self._model.get_field("utc_date_created")

    @property
    def utc_date_modified(self) -> str:
        """
        UTC modified datetime, e.g. `2021-12-31 19:18:11.939Z`.
        """
        return self._model.get_field("utc_date_modified")

    @require_setup_prop
    @property
    def attributes(self) -> Attributes:
        """
        Getter/setter for attributes, both owned and inherited.

        :setter: Sets list of owned attributes, replacing the existing list
        """
        return self._attributes

    @attributes.setter
    def attributes(self, val: list[BaseAttribute]):
        self._attributes._setattr(val)

    @property
    def labels(self) -> Labels:
        """
        Getter for labels, accessed as combined list or filtered by
        owned vs inherited.
        """
        return self._labels

    @property
    def relations(self) -> Relations:
        """
        Getter for labels, accessed as combined list or filtered by
        owned vs inherited.
        """
        return self._relations

    @require_setup_prop
    @property
    def branches(self) -> Branches:
        """
        Getter/setter for branches, both parent and child.
        """
        return self._branches

    @branches.setter
    def branches(self, val: list[Branch]):
        self._branches._setattr(val)

    @require_setup_prop
    @property
    def parents(self) -> ParentNotes:
        """
        Getter/setter for parent notes.

        :setter: Sets set of parent notes, replacing the existing set
        """
        return self._parents

    @parents.setter
    def parents(self, val: set[Note]):
        self._parents._setattr(val)

    @require_setup_prop
    @property
    def children(self) -> ChildNotes:
        """
        Getter/setter for child notes.

        :setter: Sets list of parent notes, replacing the existing list
        """
        return self._children

    @children.setter
    def children(self, val: list[Note]):
        self._children._setattr(val)

    @require_setup_prop
    @property
    def content(self) -> str | bytes:
        """
        Getter/setter for note content.
        """
        return self._content._get()

    @content.setter
    def content(self, val: str | bytes | IO):
        self._content._set(val)

    @property
    def content_str(self) -> str:
        """
        Type-safe getter for text note content.
        """
        content = self.content

        if not isinstance(content, str):
            raise ValueError(
                f"Invalid content type {type(content)} for note with is_string={self.is_string}"
            )

        return content

    @property
    def content_bin(self) -> bytes:
        """
        Type-safe getter for binary note content.
        """
        content = self.content

        if not isinstance(content, bytes):
            raise ValueError(
                f"Invalid content type {type(content)} for note with is_string={self.is_string}"
            )

        return content

    @property
    def blob_id(self) -> str:
        """
        Getter for `blobId`, a digest of the note content.
        """
        self._model.setup_check()
        return self._content.blob_id

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

    def get(self, name: str, default: Any = None) -> str | None:
        """
        Get value of first attribute with provided name.
        """
        attr = self.labels.get(name)
        if attr is None:
            return default
        return attr.value

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

    def transmute[NoteT: Note](self, note_cls: type[NoteT]) -> NoteT:
        """
        Change this note's base to the provided class and return it.
        This is useful for converting a {obj}`Note` instance to a subclass
        thereof with custom convenience APIs.

        ```{note}
        Has a side effect of committing any changes to this note to Trilium.
        ```
        """

        # commit changes to this note so state is retained
        self.flush()

        return note_cls(note_id=self.note_id, session=self.session)

    def export_zip(
        self,
        dest_path: Path,
        export_format: Literal["html", "markdown"] = "html",
    ):
        """
        Export this note subtree to zip file.

        :param dest_path: Destination .zip file
        :param export_format: Format of exported HTML notes
        """
        assert (
            self.note_id is not None
        ), f"Source note {self.str_short} must have a note_id for export"

        assert export_format in {"html", "markdown"}

        dest_path = (
            dest_path if isinstance(dest_path, Path) else Path(dest_path)
        )

        url = f"{self.session._base_path}/notes/{self.note_id}/export"
        params = {"format": export_format}
        response = requests.get(
            url, headers=self.session._etapi_headers, params=params, stream=True
        )

        assert response.status_code == 200

        zip_file: bytes = response.content
        assert isinstance(zip_file, bytes)

        with dest_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=8192):
                fh.write(chunk)

    def import_zip(
        self,
        src_path: Path,
    ) -> Note:
        """
        Import note subtree from zip file, adding the imported root as a
        child of this note and returning it.

        :param src_path: Source .zip file
        """

        # flush any changes since we need to refresh later
        self.flush()

        src_path = src_path if isinstance(src_path, Path) else Path(src_path)

        assert (
            self.note_id is not None
        ), f"Destination note {self.str_short} must have a note_id for import"

        zip_file: bytes

        # read input zip
        with src_path.open("rb") as fh:
            zip_file = fh.read()

        headers = self._session._etapi_headers.copy()
        headers["Content-Type"] = "application/octet-stream"
        headers["Content-Transfer-Encoding"] = "binary"

        url = f"{self.session._base_path}/notes/{self.note_id}/import"
        response = requests.post(url, headers=headers, data=zip_file)

        assert response.status_code == 201

        # convert response to model
        response_model = NoteWithBranch(**response.json())
        assert response_model.note is not None

        # refresh note since now it has another child
        self.refresh()

        # create imported note using response_model
        imported_note = Note._from_model(
            response_model.note, session=self.session
        )

        return imported_note

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
        self._parents = ParentNotes(self)
        self._children = ChildNotes(self)
        self._content = Content(self)

        # create accessors
        self._labels = Labels(self)
        self._relations = Relations(self)

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
    def _from_id(cls, note_id: str, session: Session | None = None) -> Note:
        return Note(note_id=note_id, session=session)

    @classmethod
    def _from_model(
        cls, model: EtapiNoteModel, session: Session | None = None
    ) -> Note:
        return Note(
            note_id=model.note_id, session=session, _model_backing=model
        )

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

            if self.note_id is not None and self.note_id != "root":
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
