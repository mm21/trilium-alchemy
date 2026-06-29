from __future__ import annotations

import mimetypes
import os
from graphlib import TopologicalSorter
from io import IOBase
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Iterable, Self, Sequence, overload

import requests
from trilium_client.exceptions import NotFoundException
from trilium_client.models.attachment import Attachment as EtapiAttachmentModel
from trilium_client.models.create_attachment import CreateAttachment
from trilium_client.models.note import Note as EtapiNoteModel

from ..entity.entity import BaseEntity, OrderedEntity
from ..entity.model import (
    BaseDriver,
    BaseEntityModel,
    StatefulExtension,
    WriteOnceDescriptor,
)
from ..exceptions import _assert_validate
from ..session import Session, normalize_session
from .content import BlobState, get_digest
from .extension import BaseEntityList

if TYPE_CHECKING:
    from .note import Note

__all__ = [
    "Attachment",
    "Attachments",
]


class AttachmentDriver(BaseDriver[EtapiAttachmentModel]):
    @property
    def attachment(self) -> Attachment:
        assert isinstance(self.entity, Attachment)
        return self.entity

    def fetch(self) -> EtapiAttachmentModel | None:
        assert self.attachment.attachment_id
        model: EtapiAttachmentModel | None = None

        try:
            model = self.session.api.get_attachment_by_id(self.attachment.attachment_id)
        except NotFoundException:
            pass

        return model

    def flush_create(self, sorter: TopologicalSorter) -> EtapiAttachmentModel:
        _ = sorter
        assert self.attachment._note
        assert self.attachment._note.note_id
        assert self.attachment._model.working_data

        # content is pushed separately by the content extension, so create
        # with empty content here
        model = CreateAttachment(
            ownerId=self.attachment._note.note_id,
            content="",
            **self.attachment._model.working_data,
        )

        new_model = self.session.api.post_attachment(model)
        return new_model

    def flush_update(self, sorter: TopologicalSorter) -> EtapiAttachmentModel:
        _ = sorter
        assert self.attachment.attachment_id

        # only role/mime/title/position are patchable; the binary blob is
        # handled separately by the content extension
        model = EtapiAttachmentModel(**self.attachment._model.get_changed_fields())
        new_model = self.session.api.patch_attachment_by_id(
            self.attachment.attachment_id, model
        )
        return new_model

    def flush_delete(self, sorter: TopologicalSorter):
        _ = sorter
        assert self.attachment.attachment_id
        self.session.api.delete_attachment_by_id(self.attachment.attachment_id)


class AttachmentModel(BaseEntityModel):
    @property
    def etapi_model(self) -> type[EtapiAttachmentModel]:
        return EtapiAttachmentModel

    @property
    def driver_cls(self) -> type[AttachmentDriver]:
        return AttachmentDriver

    @property
    def entity_id_field(self) -> str:
        return "attachment_id"

    @property
    def update_fields(self) -> list[str]:
        return ["role", "mime", "title", "position"]

    @property
    def default_fields(self) -> dict:
        return {"role": "image", "mime": "image", "title": "", "position": 10}


class AttachmentContent(StatefulExtension[EtapiAttachmentModel]):
    """
    Interface to an attachment's binary content, modeled on {obj}`Content` but bytes-
    only.
    """

    _backing: BlobState
    _working: BlobState

    def __init__(self, entity: BaseEntity):
        super().__init__(entity)
        self._backing = BlobState()
        self._working = BlobState()

    @property
    def _attachment(self) -> Attachment:
        assert isinstance(self._entity, Attachment)
        return self._entity

    @property
    def blob_id(self) -> str:
        digest = self._working.digest or self._backing.digest
        assert digest is not None
        return digest

    @property
    def _is_changed(self) -> bool:
        if self._working.blob is None:
            return False

        assert self._backing.digest is not None
        assert self._working.digest is not None

        return self._backing.digest != self._working.digest

    def _setattr(self, obj: Any):
        _ = obj
        raise NotImplementedError

    def _setup(self, model: EtapiAttachmentModel | None):
        if model is None:
            # newly created, initialize to empty content
            self._backing.blob = b""
            self._backing.digest = get_digest(self._backing.blob)
        else:
            assert (
                model.blob_id is not None
            ), "Digest not provided in attachment model; please upgrade your Trilium version"
            self._backing.digest = model.blob_id

    def _teardown(self):
        [state.reset() for state in [self._backing, self._working]]

    def _get(self) -> bytes:
        if self._working.blob is not None:
            blob = self._working.blob
        else:
            self._fetch_check()
            blob = self._backing.blob

        assert isinstance(blob, bytes)
        return blob

    def _set(self, blob: bytes):
        assert isinstance(
            blob, bytes
        ), f"Attachment content must be bytes, got {type(blob)}"

        self._working.blob = blob
        self._working.digest = get_digest(blob)

        # may change clean/dirty state, so reevaluate
        self._attachment._check_state()

    def _fetch_check(self):
        if self._backing.blob is None:
            self._fetch()

    def _fetch(self):
        response = requests.get(
            self._url, headers=self._attachment._session._etapi_headers
        )
        assert response.status_code == 200
        self._backing.blob = response.content

    def _flush(self) -> EtapiAttachmentModel:
        blob = self._working.blob
        assert isinstance(blob, bytes)

        digest = self._working.digest
        assert digest is not None

        headers = self._attachment._session._etapi_headers.copy()
        headers["Content-Type"] = "application/octet-stream"
        headers["Content-Transfer-Encoding"] = "binary"

        # generated ETAPI client only supports text, so make request manually
        response = requests.put(self._url, headers=headers, data=blob)
        assert (
            response.status_code == 204
        ), f"PUT {self._url} response: {response.status_code}"

        self._backing = self._working
        self._working = BlobState()

        # refresh attachment model to update blob_id and modified time
        new_model = self._attachment._model.driver.fetch()
        assert isinstance(new_model, EtapiAttachmentModel)

        return new_model

    @property
    def _url(self) -> str:
        base_path = self._attachment._session._base_path
        return f"{base_path}/attachments/{self._attachment.attachment_id}/content"


class Attachment(OrderedEntity[AttachmentModel, EtapiAttachmentModel]):
    """
    Encapsulates an attachment, a named binary blob owned by a {obj}`Note`.

    Trilium only supports image attachments.

    Add to a note using its {obj}`Note.attachments` list. An attachment can be
    created from raw `bytes`{l=python} (requires a `title`{l=python}), a
    {obj}`pathlib.Path`, or a binary file handle:

    ```
    note.attachments = [
        Attachment(title="image.png", content=b"..."),
        Path("image.png"),
        open("image.png", "rb"),
    ]
    ```
    """

    # note which owns this attachment, ensuring only one note is assigned
    _note = WriteOnceDescriptor["Note | None"]("_note_obj")
    _note_obj: Note | None = None

    _content_ext: AttachmentContent

    def __new__(cls, *_, **kwargs) -> Self:
        return super().__new__(
            cls,
            session=kwargs.get("session"),
            entity_id=kwargs.get("_attachment_id"),
        )

    @overload
    def __init__(
        self,
        content: bytes,
        *,
        title: str,
        role: str = "image",
        mime: str | None = None,
        session: Session | None = None,
        **kwargs,
    ): ...

    @overload
    def __init__(
        self,
        content: IO[bytes] | Path | None = None,
        *,
        title: str | None = None,
        role: str = "image",
        mime: str | None = None,
        session: Session | None = None,
        **kwargs,
    ): ...

    def __init__(
        self,
        content: bytes | IO[bytes] | Path | None = None,
        *,
        title: str | None = None,
        role: str = "image",
        mime: str | None = None,
        session: Session | None = None,
        **kwargs,
    ):
        attachment_id: str | None = kwargs.get("_attachment_id")
        owning_note: Note | None = kwargs.get("_owning_note")
        backing_model: EtapiAttachmentModel | None = kwargs.get("_backing_model")
        super().__init__(entity_id=attachment_id, session=session)

        # set owning note if known already
        if owning_note is not None:
            self._note = owning_note

        if backing_model is not None:
            # loading from server; metadata/content come from the model
            return

        # resolve content/title/mime for a newly created attachment
        blob: bytes | None = None
        name: str | None = None
        if content is not None:
            blob, name = _normalize_content(content)

        # title is required, but may be derived from a filename
        resolved_title = title if title is not None else name
        if resolved_title is None:
            raise ValueError(
                "Attachment requires a title (pass title=, a Path, or a file "
                "handle with a name)"
            )

        # resolve mime, guessing from filename/title and enforcing image-only
        resolved_mime = mime
        if resolved_mime is None:
            guess_name = name or resolved_title
            guessed, _ = mimetypes.guess_type(guess_name)
            resolved_mime = guessed if guessed is not None else "image"

        if not (resolved_mime == "image" or resolved_mime.startswith("image/")):
            raise ValueError(
                f"Trilium only supports image attachments, got mime "
                f"'{resolved_mime}'"
            )

        self.role = role
        self.title = resolved_title
        self.mime = resolved_mime

        if blob is not None:
            self.content = blob

    @property
    def attachment_id(self) -> str | None:
        """
        Getter for `attachmentId`, or `None` if not created yet.
        """
        return self._entity_id

    @property
    def note(self) -> Note:
        """
        Getter for note which owns this attachment.

        :raises ValueError: If note has not been set
        """
        if not self._note:
            raise ValueError(f"Attachment {self} has not been assigned to a note")
        return self._note

    @property
    def role(self) -> str:
        """
        Getter/setter for attachment role, e.g. `"image"`{l=python}.
        """
        return self._model.get_field("role", str)

    @role.setter
    def role(self, val: str):
        self._model.set_field("role", val)

    @property
    def mime(self) -> str:
        """
        Getter/setter for MIME type.
        """
        return self._model.get_field("mime", str)

    @mime.setter
    def mime(self, val: str):
        self._model.set_field("mime", val)

    @property
    def title(self) -> str:
        """
        Getter/setter for attachment title.
        """
        return self._model.get_field("title", str)

    @title.setter
    def title(self, val: str):
        self._model.set_field("title", val)

    @property
    def content(self) -> bytes:
        """
        Getter/setter for attachment content as `bytes`{l=python}.
        """
        return self._content_ext._get()

    @content.setter
    def content(self, val: bytes):
        self._content_ext._set(val)

    @property
    def blob_id(self) -> str:
        """
        Getter for `blobId`, a digest of the attachment content.
        """
        return self._content_ext.blob_id

    @property
    def utc_date_modified(self) -> str | None:
        """
        UTC modified datetime, e.g. `2021-12-31 19:18:11.939Z`.
        """
        return self._model.get_field("utc_date_modified", str, allow_none=True)

    @property
    def position(self) -> int:
        """
        Getter for position of this attachment.

        ```{note}
        This is maintained automatically based on the order of this attachment
        in its note's {obj}`Note.attachments` list.
        ```
        """
        return self._position

    def save(self, path: str | Path):
        """
        Write attachment content to the provided path.
        """
        Path(path).write_bytes(self.content)

    @property
    def _position(self) -> int:
        return self._model.get_field("position", int)

    @_position.setter
    def _position(self, val: int):
        self._model.set_field("position", val)

    @classmethod
    def _from_id(cls, entity_id: str, session: Session | None = None) -> Self:
        session = normalize_session(session)
        model = session.api.get_attachment_by_id(entity_id)
        return cls._from_model(model, session=session)

    @classmethod
    def _from_model(
        cls,
        model: EtapiAttachmentModel,
        session: Session | None = None,
        owning_note: Note | None = None,
    ) -> Self:
        attachment = cls(
            session=session,
            _attachment_id=model.attachment_id,
            _backing_model=model,
            _owning_note=owning_note,
        )
        return attachment

    @property
    def _model_cls(self) -> type[AttachmentModel]:
        return AttachmentModel

    @property
    def _str_short(self) -> str:
        attachment_id = f"'{self.attachment_id}'" if self.attachment_id else None
        title = self._model.get_field("title", str) if self._model.setup_done else "?"
        return f"Attachment(title='{title}', attachment_id={attachment_id})"

    @property
    def _str_safe(self) -> str:
        return f"Attachment(attachment_id={self._entity_id}, id={id(self)})"

    @property
    def _dependencies(self) -> set[BaseEntity]:
        assert self._note
        return {self._note}

    @property
    def _associated_entities(self) -> Sequence[BaseEntity]:
        return []

    def _init(self):
        self._content_ext = AttachmentContent(self)

    def _setup(self, model: EtapiAttachmentModel):
        assert model.owner_id

        from .note import Note

        if self._note_obj is None:
            self._note = Note(note_id=model.owner_id, session=self._session)
        else:
            assert self._note_obj.note_id == model.owner_id

    def _flush_check(self):
        _assert_validate(self._note is not None, "Attachment not assigned to note")

    def _flush_prep(self):
        pass

    def _delete(self):
        super()._delete()

        if self._note is not None:
            if self in self._note.attachments:
                self._note.attachments.remove(self)


class Attachments(BaseEntityList[Attachment]):
    """
    Interface to a note's attachments, modeled as a list.

    Items assigned may be an {obj}`Attachment`, a {obj}`pathlib.Path`, or a binary file
    handle with a `.name`{l=python}. Raw `bytes`{l=python} is not accepted here since a
    title can't be derived; construct an {obj}`Attachment` explicitly with a title
    instead.
    """

    _child_cls = Attachment
    _owner_field = "_note"

    # set of attachments reflecting server state, used to detect changes
    _backing_set: set[Attachment] | None = None

    # whether the working list has been populated from the server yet
    _fetched: bool = False

    def __str__(self):
        if self._entity_list is not None and len(self._entity_list) > 0:
            return "\n".join(str(e) for e in self._entity_list)
        return "No attachments"

    @property
    def _norm_entity_list(self) -> list[Attachment]:
        if self._entity_list is None:
            # populate lazily from the server on first access
            self._fetch()
        assert self._entity_list is not None
        return self._entity_list

    @property
    def _is_changed(self) -> bool:
        if self._entity_list is None:
            # never accessed/modified: can't have changed
            return False

        assert self._backing_set is not None

        if set(self._entity_list) != self._backing_set:
            return True

        return any(attachment._is_dirty for attachment in self._entity_list)

    def _setup(self, model: EtapiNoteModel | None):
        if model is None:
            # newly created note: no attachments to fetch
            self._entity_list = []
            self._backing_set = set()
            self._fetched = True

    def _teardown(self):
        super()._teardown()
        self._backing_set = None
        self._fetched = False

    def _fetch(self):
        """
        Populate working list from the server.
        """
        assert self._note.note_id is not None

        self._entity_list = []
        for model in self._note._session.api.get_note_attachments(self._note.note_id):
            self._entity_list.append(
                Attachment._from_model(
                    model,
                    session=self._note._session,
                    owning_note=self._note,
                )
            )

        self._entity_list.sort(key=lambda a: a._position)
        self._backing_set = set(self._entity_list)
        self._fetched = True

    def _flush(self) -> None:
        # the attachment entities flush themselves; just snapshot the new
        # server state so the note returns to clean
        self._backing_set = set(self._norm_entity_list)
        return None

    def _collect_flush_entities(self) -> set[Attachment]:
        """
        Return attachments which may need flushing: those currently in the list plus any
        previously-known (now possibly deleted) ones.

        Empty if not yet materialized.
        """
        if self._entity_list is None:
            return set()
        return set(self._entity_list) | (self._backing_set or set())

    def _normalize(self, value: Any) -> Attachment:
        return Attachment(content=value, session=self._note._session)

    def _setattr(self, obj: Iterable[Attachment | Path | IO[bytes]]):
        if self is obj:
            return
        normalized_list = [self._invoke_normalize(e) for e in obj]
        super()._setattr(normalized_list)
        self._note._check_state()

    def __setitem__(self, i: int | slice, value: Any):
        if isinstance(i, slice):
            assert isinstance(value, Iterable)
            value = [self._invoke_normalize(e) for e in value]
        else:
            value = self._invoke_normalize(value)
        super().__setitem__(i, value)
        self._note._check_state()

    def __delitem__(self, i: int | slice):
        super().__delitem__(i)
        self._note._check_state()

    def insert(self, index: int, value: Any):
        super().insert(index, self._invoke_normalize(value))
        self._note._check_state()


def _normalize_content(
    content: bytes | IO[bytes] | Path | str,
) -> tuple[bytes, str | None]:
    """
    Resolve a content spec to `(blob, name)` where `name` is the filename to derive
    title/mime from, or `None` if not available.
    """
    if isinstance(content, (str, os.PathLike)):
        # Path (or path-like): read bytes in binary, derive name from filename
        path = Path(content)
        return path.read_bytes(), path.name
    elif isinstance(content, (IO, IOBase)):
        # binary file handle: read bytes, derive name from .name if present
        blob = content.read()
        assert isinstance(
            blob, bytes
        ), f"Attachment content must be binary, got {type(blob)}"
        name = getattr(content, "name", None)
        return blob, os.path.basename(name) if name else None
    elif isinstance(content, bytes):
        return content, None
    else:
        raise ValueError(
            f"Invalid attachment content type {type(content)}; "
            "expected bytes, binary file handle, or Path"
        )
