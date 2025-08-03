from __future__ import annotations

import base64
import copy
import hashlib
import string
from abc import ABCMeta
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Generator, Literal, Self, cast

import requests
from trilium_client.exceptions import NotFoundException
from trilium_client.models.note import Note as EtapiNoteModel
from trilium_client.models.note_with_branch import NoteWithBranch

from ..attribute import BaseAttribute, Label, Relation
from ..branch import Branch
from ..entity.entity import BaseEntity, normalize_entities
from ..entity.model import require_setup_prop
from ..exceptions import _assert_validate
from ..session import Session
from ..utils import base_n_hash
from .attributes.attributes import Attributes
from .attributes.labels import Labels
from .attributes.relations import Relations
from .branches import Branches, ChildNotes, ParentNotes
from .content import Content
from .model import NoteModel

__all__ = [
    "Note",
]


STRING_NOTE_TYPES = [
    "text",
    "code",
    "search",
    "relationMap",
    "noteMap",
    "render",
    "book",
    "mermaid",
    "canvas",
    "webView",
    "mindMap",
    "geoMap",
]
"""
Keep in sync with isStringNote() (src/services/utils.js).
"""

BIN_NOTE_TYPES = [
    "file",
    "image",
]
"""
Binary note types.
"""

NOTE_TYPES = STRING_NOTE_TYPES + BIN_NOTE_TYPES
"""
All note types.
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

NOTE_TYPES_MIME_NA = [
    "search",
    "noteMap",
    "render",
    "book",
    "webView",
]
"""
Note types to which mime is not applicable (empty string).
"""

NOTE_TYPES_MIME_FIXED = {
    "relationMap": "application/json",
    "mermaid": "text/plain",
    "canvas": "application/json",
    "mindMap": "application/json",
    "geoMap": "application/json",
}
"""
Note types which have a fixed mime type.
"""


def is_string(note_type: str, mime: str) -> bool:
    """
    Encapsulates logic for checking if a note is considered string type
    according to Trilium.

    This should be generally kept in sync with
    `src/services/utils.js:isStringNote()`, although checking if not a binary
    type so as to be more future-proof for when other string types are added.
    """
    return (
        note_type not in BIN_NOTE_TYPES
        or mime.startswith("text/")
        or mime in STRING_MIME_TYPES
    )


def id_hash(seed: str) -> str:
    """
    Return entity id given seed. Ensures entity ids have a consistent amount of
    entropy by being of the same length and character distribution, derived
    from a 128-bit hash of the seed.

    The hash is mapped to "base62" (a-z, A-Z, 0-9) with no loss in entropy.
    """
    chars = string.ascii_letters + string.digits
    return base_n_hash(seed.encode(encoding="utf-8"), chars)


def id_hash_legacy(seed: str) -> str:
    """
    Legacy implementation of `id_hash()`. Possibly useful for migrating to
    the new hash mechanism. To be removed before version 1.0.

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

    # TODO: add:
    # type NoteType = Literal["text", "code", ...]
    def __init__(
        self,
        title: str | None = None,
        note_type: str | None = None,
        mime: str | None = None,
        *,
        attributes: Iterable[BaseAttribute] | None = None,
        parents: Iterable[Note | Branch] | Note | Branch | None = None,
        children: Iterable[Note | Branch] | None = None,
        content: str | bytes | IO | None = None,
        note_id: str | None = None,
        template: Note | type[Note] | None = None,
        session: Session | None = None,
        **kwargs,
    ):
        """
        :param title: Note title
        :param note_type: Note type, default `text`; one of: `"text"`{l=python}, `"code"`{l=python}, `"relationMap"`{l=python}, `"search"`{l=python}, `"render"`{l=python}, `"book"`{l=python}, `"mermaid"`, `"canvas"`, `"file"`{l=python}, `"image"`{l=python}
        :param mime: MIME type, default `text/html`; needs to be specified only for note types `"text"`{l=python}, `"code"`{l=python}, `"file"`{l=python}, `"image"`{l=python}
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

        init_done = self._init_done

        # invoke Entity init
        super().__init__(
            entity_id=note_id,
            session=session,
            model_backing=model_backing,
        )

        if init_done:
            assert note_id is not None
            assert self.note_id == note_id

            # ensure not attempting to set fields when already initialized
            fields_check = {
                "title": title,
                "note_type": note_type,
                "mime": mime,
                "parents": parents,
                "children": children,
                "attributes": attributes,
                "content": content,
                "template": template,
            }
            fields_err = [k for k, v in fields_check.items() if v is not None]
            assert (
                len(fields_err) == 0
            ), f"Attempt to set fields when note already initialized: {fields_err}"

            return

        def combine_lists[T](*lists: list[T] | None) -> list[T] | None:
            result: list[T] | None = None
            for lst in lists:
                if lst is not None:
                    if result is None:
                        result = []
                    result += lst
            return result

        # get container from subclass if applicable
        init_container = self._init_hook(
            note_id, note_id_seed_final, force_leaf
        )

        def normalize_mime(
            title: str | None, note_type: str | None, mime: str | None
        ) -> str | None:
            """
            Return correct mime given note_type, validating if it was passed
            by user.
            """

            if note_type is None:
                return None
            elif note_type in NOTE_TYPES_MIME_NA:
                mime_norm = ""
            elif note_type in NOTE_TYPES_MIME_FIXED:
                mime_norm = NOTE_TYPES_MIME_FIXED[note_type]
            elif mime is not None:
                mime_norm = mime
            else:
                mime_norm = "text/html" if note_type == "text" else None

            # if passed by user, validate
            if mime is not None:
                assert (
                    mime == mime_norm
                ), f"Got invalid mime '{mime}' from user for note '{title}' of type '{note_type}', expected '{mime_norm}'"

            return mime_norm

        # aggregate fields to set
        title_set = title or init_container.title
        note_type_set = note_type or init_container.note_type
        mime_set = normalize_mime(
            title_set, note_type_set, mime or init_container.mime
        )
        content_set = content or init_container.content
        attributes_set = combine_lists(attributes, init_container.attributes)
        parents_set: Iterable[Note | Branch] | None = (
            None
            if parents is None
            else cast(Iterable[Note | Branch], normalize_entities(parents))
        )
        children_set = combine_lists(children, init_container.children)

        if template is not None:
            # create and append new relation
            template_relation = _normalize_template(template, session)

            if attributes_set is None:
                attributes_set = [template_relation]
            else:
                attributes_set.append(template_relation)

        # set fields

        if title_set is not None:
            self.title = title_set

        if note_type_set is not None:
            self.note_type = note_type_set

        if mime_set is not None:
            self.mime = mime_set

        # set content after type/mime to determine expected content type
        # (text or binary)
        if content_set is not None:
            self.content = content_set

        if attributes_set is not None:
            self.attributes.owned = attributes_set

        if parents_set is not None:
            self.parents = parents_set

        if children_set is not None:
            self.children = children_set

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

    def __contains__(self, label: str) -> bool:
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
        if not val in NOTE_TYPES:
            self.session._logger.warning(f"Unknown note_type: {val}")
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
        Getter for branches, both parents (`.parents`) and children
        (`.children`).
        """
        return self._branches

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

        :setter: Sets list of child notes, replacing the existing list
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
        Type-safe getter/setter for text note content.
        """
        content = self.content

        if not isinstance(content, str):
            raise ValueError(
                f"Invalid content type {type(content)} for note with is_string={self.is_string}"
            )

        return content

    @content_str.setter
    def content_str(self, val: str):
        self.content = val

    @property
    def content_bin(self) -> bytes:
        """
        Type-safe getter/setter for binary note content.
        """
        content = self.content

        if not isinstance(content, bytes):
            raise ValueError(
                f"Invalid content type {type(content)} for note with is_string={self.is_string}"
            )

        return content

    @content_bin.setter
    def content_bin(self, val: bytes):
        self.content = val

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

    def get(self, name: str, default: str | None = None) -> str | None:
        """
        Get value of first label with provided name, or `None` if no such
        label exists.
        """
        attr = self.labels.get(name)
        return default if attr is None else attr.value

    def copy(self, deep: bool = False) -> Note:
        """
        Return a copy of this note, including its title, type, MIME,
        attributes, and content.

        If `deep` is `False`{l=python}, child notes are cloned to the
        returned copy. Otherwise, child notes are recursively deep copied.

        ```{note}
        The returned copy still needs to be placed in the tree hierarchy
        (added as a child of another note) before `Session.flush()`
        is invoked.
        ```
        """
        return CopyContext().copy(self, deep=deep)

    def sync_template(self, template: Note):
        """
        Update this note to match the provided template:

        - Set note type and MIME
        - Set content if empty
        - Recursively deep copy missing child notes, matched by title
        """

        copy_context = CopyContext()

        def find_child(child: Note, dest: Note) -> Note | None:
            """
            Find child by title.
            """
            for dest_child in dest.children:
                if child.title == dest_child.title:
                    return dest_child
            return None

        def recurse(src: Note, dest: Note):
            for src_child in src.children:
                dest_child = find_child(src_child, dest)

                if dest_child is not None:
                    copy_context.add_mapping(src_child, dest_child)
                    recurse(src_child, dest_child)

        # first, recursively populate copy context with all matched notes
        recurse(template, self)

        self._sync_subtree(template, copy_context)

    def transmute[NoteT: Note](self, note_cls: type[NoteT]) -> NoteT:
        """
        Change this note's base to the provided class and return it.
        This is useful for converting a {obj}`Note` instance to a subclass
        thereof with custom convenience APIs.

        ```{note}
        Has a side effect of committing any changes to this note to Trilium.
        ```
        """

        if self._is_dirty:
            # commit changes to this note so state is retained
            self.flush()

        return note_cls(note_id=self.note_id, session=self.session)

    def export_zip(
        self,
        dest_file: Path,
        export_format: Literal["html", "markdown"] = "html",
        overwrite: bool = False,
    ):
        """
        Export this note subtree to zip file.

        :param dest_file: Destination .zip file
        :param export_format: Format of exported HTML notes
        :param overwrite: Whether to overwrite destination path if it exists
        """
        assert (
            self.note_id is not None
        ), f"Source note {self.str_short} must have a note_id for export"
        assert export_format in {"html", "markdown"}

        dest_file_norm = (
            dest_file if isinstance(dest_file, Path) else Path(dest_file)
        )

        if dest_file_norm.exists() and not overwrite:
            raise ValueError(
                f"Path {dest_file_norm} exists and overwrite=False"
            )

        url = f"{self.session._base_path}/notes/{self.note_id}/export"
        params = {"format": export_format}
        response = requests.get(
            url, headers=self.session._etapi_headers, params=params, stream=True
        )

        assert response.status_code == 200

        zip_file: bytes = response.content
        assert isinstance(zip_file, bytes)

        with dest_file_norm.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=8192):
                fh.write(chunk)

    def import_zip(
        self,
        src_file: Path,
    ) -> Note:
        """
        Import note subtree from zip file, adding the imported root as a
        child of this note and returning it.

        :param src_file: Source .zip file
        """

        # flush any changes since we need to refresh later
        self.flush()

        src_file_norm = (
            src_file if isinstance(src_file, Path) else Path(src_file)
        )

        assert (
            self.note_id is not None
        ), f"Destination note {self.str_short} must have a note_id for import"

        zip_file: bytes

        # read input zip
        with src_file_norm.open("rb") as fh:
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

    def walk(self) -> Generator[Note, None, None]:
        """
        Yield this note and all children recursively. Each note will only
        occur once (clones are skipped).
        """
        yield from self._walk(set())

    def flush(self):
        """
        Flush note along with its owned attributes.
        """

        # collect set of entities
        flush_set: set[BaseEntity] = {attr for attr in self.attributes.owned}
        flush_set.add(self)

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
    def _associated_entities(self) -> list[BaseEntity]:
        return list(self.branches) + list(self.attributes.owned)

    @property
    def _str_summary_extra_pre(self) -> list[str]:
        """
        Get note paths for summary print.
        """
        paths_ret: list[str] = []

        for path in self.paths:
            if len(path) > 1:
                paths_ret.append(
                    " > ".join(
                        [f"'{note._title_escape}'" for note in path[:-1]]
                    )
                )

        return sorted(paths_ret)

    @property
    def _str_summary_extra_post(self) -> list[str]:
        """
        Get content state for summary print.
        """
        blob_ids: list[str] = []

        if self._content._is_changed and not self._is_create:
            blob_ids.append(f"'{self._content._backing.digest}'")

        blob_ids.append(f"'{self._content.blob_id}'")

        return [f"blob_id={'->'.join(blob_ids)}".join(["{", "}"])]

    @property
    def _str_short(self):
        note_id = f"'{self.note_id}'" if self.note_id else None
        return f"Note('{self._title_escape}', note_id={note_id})"

    @property
    def _str_safe(self):
        return f"Note(note_id={self._entity_id}, id={id(self)})"

    @property
    def _title_escape(self) -> str:
        return self.title.replace("'", "\\'")

    @classmethod
    def _get_note_id(cls, note_id: str | None) -> tuple[str | None, str | None]:
        return (note_id, None)

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

    def _delete(self):
        super()._delete()

        # also delete each parent branch so parents' child lists are updated
        for branch in self.branches.parents:
            branch.delete()

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

    def _sync_subtree(self, src: Note, copy_context: CopyContext):
        """
        Recursively sync this note with source, deep copying new notes as
        necessary.
        """

        self.note_type = src.note_type
        self.mime = src.mime

        existing_children: list[Branch] = [b for b in self.branches.children]
        new_children: list[Branch] = []

        def find_child(src_child: Note) -> Branch | None:
            """
            Find child by title and pop from existing children list.
            """
            for i, branch in enumerate(existing_children):
                if src_child.title == branch.child.title:
                    return existing_children.pop(i)
            return None

        # traverse children and identify which ones to copy
        for branch in src.branches.children:
            # check if a child note with this title already exists, and use it
            # if so
            existing_branch = find_child(branch.child)
            add_branch: Branch

            if existing_branch is None:
                child_copy = copy_context.copy(branch.child, deep=True)
                child_branch = self.branches.children.lookup_branch(child_copy)

                # use existing branch or create new
                add_branch = child_branch or Branch(
                    self, child_copy, prefix=branch.prefix, session=self.session
                )
            else:
                add_branch = existing_branch
                add_branch.child._sync_subtree(branch.child, copy_context)

            new_children.append(add_branch)

        # append any remaining children at end
        new_children += existing_children

        # assign new children
        self.branches.children = new_children

        # assign content if empty
        if len(self.content) == 0:
            self.content = src.content

    @classmethod
    def _exists(cls, session: Session, note_id: str) -> bool:
        """
        Check whether note given by note_id exists.
        """
        try:
            _ = session.api.get_note_by_id(note_id)
        except NotFoundException:
            return False
        else:
            return True

    def _walk(self, seen_notes: set[Note]) -> Generator[Note, None, None]:
        yield self

        for child in self.children:
            if not child in seen_notes:
                seen_notes.add(child)
                yield from child._walk(seen_notes)

    def _cleanup_positions(self):
        self._attributes.owned._set_positions(cleanup=True)
        self._branches.children._set_positions(cleanup=True)


@dataclass
class InitContainer:
    title: str | None = None
    note_type: str | None = None
    mime: str | None = None
    attributes: list[BaseAttribute] | None = None
    children: list[Note | Branch] | None = None
    content: str | bytes | IO | None = None


class CopyContext:
    """
    Maintain a mapping of (destination note's id) -> (new Note)
    to properly recreate any clones.

    Use id() since note_id may not exist yet, and there cannot be
    multiple Note instances with same note_id.
    """

    note_map: dict[int, Note]

    def __init__(self):
        self.note_map = dict()

    def copy(self, note: Note, deep: bool = False) -> Note:
        # check if we already made a copy of this note
        if id(note) in self.note_map:
            # reuse note since it's cloned
            note_copy = self.note_map[id(note)]
        else:
            # create new note
            note_copy = Note(
                title=note.title,
                note_type=note.note_type,
                mime=note.mime,
                session=note.session,
            )

            # add to map
            self.note_map[id(note)] = note_copy

            # do copy
            self._do_copy(note, note_copy, deep)

        return note_copy

    def add_mapping(self, src: Note, dest: Note):
        if id(src) in self.note_map:
            assert self.note_map[id(src)] is dest
        else:
            self.note_map[id(src)] = dest

    def _do_copy(self, src: Note, dest: Note, deep: bool):
        # copy fields
        dest.title = src.title
        dest.note_type = src.note_type
        dest.mime = src.mime

        # copy attributes
        self._copy_attributes(src, dest)

        # copy children
        for branch in src.branches.children:
            # copy or clone this child
            child = self.copy(branch.child) if deep else branch.child

            # create new branch with same prefix
            dest += Branch(
                child=child,
                prefix=branch.prefix,
                session=src.session,
            )

        # copy content
        dest.content = copy.copy(src.content)

    def _copy_attributes(self, src: Note, dest: Note):
        """
        Copy owned attributes from source to destination.
        """

        for attr in src.attributes.owned:
            assert isinstance(attr, (Label, Relation))
            attr_copy: BaseAttribute

            if isinstance(attr, Label):
                attr_copy = Label(
                    attr.name,
                    value=attr.value,
                    inheritable=attr.inheritable,
                    session=src.session,
                )
            else:
                attr_copy = Relation(
                    attr.name,
                    target=attr.target,
                    inheritable=attr.inheritable,
                    session=src.session,
                )

            dest += attr_copy


def _normalize_template(
    template: Note | type[Note], session: Session | None
) -> Relation:
    from ..declarative.base import BaseDeclarativeNote

    target: Note
    template_cls: type[Note] = get_cls(template)

    if isinstance(template, ABCMeta):
        # have class

        assert issubclass(
            template_cls, BaseDeclarativeNote
        ), f"Template target must be a subclass of BaseDeclarativeNote, got {template_cls}"
        assert (
            template_cls._is_singleton()
        ), f"Template target must be singleton class, got {template_cls}"

        # instantiate target
        target = template_cls(session=session)
    else:
        # have instance
        target = cast(Note, template)

    assert isinstance(
        target, Note
    ), f"Template target must be a Note, have {type(target)}"

    return Relation(
        "template",
        target,
        session=session,
    )
