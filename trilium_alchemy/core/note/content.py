from __future__ import annotations

import base64
import hashlib
import logging
from io import IOBase
from typing import IO, Any

import requests
from trilium_client.models.note import Note as EtapiNoteModel

from ..entity import BaseEntity
from ..entity.model import ExtensionDescriptor, ModelContainer
from .extension import NoteStatefulExtension

__all__ = [
    "Content",
    "ContentDescriptor",
]


class ContentDescriptor(ExtensionDescriptor):
    """
    Override `ExtensionDescriptor.__get__` to return the content itself
    via `Content._get`.
    """

    def __get__(self, container: ModelContainer, objtype=None):
        return super().__get__(container, objtype=objtype)._get()


class FileDescriptor:
    def __get__(self, content: Content, objtype=None):
        # TODO: return file descriptor?
        raise NotImplementedError()

    def __set__(self, content: Content, path_file: str):
        if content._is_string:
            mode = "r"
        else:
            mode = "rb"

        fh = open(path_file, mode)
        content._set(fh.read())


class BlobState:
    # note content in string or binary form
    blob: str | bytes | None = None

    # digest of blob, calculated locally or provided by server
    digest: str | None = None

    def reset(self):
        self.blob = None
        self.digest = None


class Content(NoteStatefulExtension):
    """
    Interface to note's content.

    Access as {obj}`Note.content`, a descriptor mapping to
    an instance of this class.

    The expected type depends on {obj}`Note.is_string`:
    - `True`{l=python}: get/set `str`{l=python}
    - `False`{l=python}: get/set `bytes`{l=python}

    Get or set content as follows:

    ```
    note.content = "<p>Hello, world!</p>"
    assert note.content == "<p>Hello, world!</p>"
    ```

    ````{todo}
    Helper `Note.file` to set content from file, automatically
    setting `mime` and `#originalFilename`.

    Example:

    ```
    note.file = "assets/my_content.html"
    ```
    ````
    """

    _backing: BlobState
    _working: BlobState

    def __init__(self, entity: BaseEntity):
        super().__init__(entity)

        self._backing = BlobState()
        self._working = BlobState()

    @property
    def blob_id(self) -> str:
        """
        Get blob id from the working model if it exists, else backing model.
        """

        digest = self._working.digest or self._backing.digest
        assert digest is not None
        return digest

    @property
    def _is_string(self):
        return self._note.is_string

    @property
    def _is_changed(self):
        """
        Return whether note content is changed, as determined by content hash
        (blobId).
        """

        if self._working.blob is None:
            # content not set by user
            return False

        assert self._backing.digest is not None
        assert self._working.digest is not None

        # efficiently check digest
        return self._backing.digest != self._working.digest

    def _setattr(self, val: Any):
        self._set(val)

    def _setup(self, model: EtapiNoteModel | None):
        """
        Setup state from Note model; defer loading content itself until
        accessed by user.
        """

        if model is None:
            # newly created, initialize to empty content
            if self._is_string:
                self._backing.blob = ""
            else:
                self._backing.blob = b""

            self._backing.digest = self._get_digest(self._backing.blob)
        else:
            # get digest from model, only fetch content if accessed by user
            assert (
                model.blob_id is not None
            ), f"Digest not provided in note model; please upgrade your Trilium version"
            self._backing.digest = model.blob_id

    def _teardown(self):
        """
        Reset all state.
        """
        [state.reset() for state in [self._backing, self._working]]

    def _get(self) -> str | bytes:
        """
        Return current content.

        The type is `str` or `bytes`, depending on whether Trilium stores the
        content as string or binary.
        """

        if self._working.blob is not None:
            # get from content set by user
            blob = self._working.blob
        else:
            # get from server
            self._fetch_check()
            blob = self._backing.blob

        assert blob is not None
        return blob

    def _set(self, blob: str | bytes | IO):
        """
        Set new content and generate digest.
        """
        blob: str | bytes = self._normalize_blob(blob)

        self._working.blob = blob
        self._working.digest = self._get_digest(blob)

        # could potentially change clean/dirty state, so reevaluate
        self._note._check_state()

    def _fetch_check(self):
        """
        Ensure note content has been fetched from server.
        """
        if self._backing.blob is None:
            self._fetch()

    def _fetch(self):
        """
        Get note content from server.
        """

        blob: str | bytes = None

        response = requests.get(
            self._url, headers=self._note._session._etapi_headers
        )
        assert response.status_code == 200

        if self._is_string:
            blob = response.text
            assert isinstance(blob, str)
        else:
            blob = response.content
            assert isinstance(blob, bytes)

        self._backing.blob = blob

    def _flush(self):
        """
        Push note content to server.
        """

        blob: str | bytes = self._working.blob
        assert blob is not None

        headers = self._note._session._etapi_headers.copy()

        logging.debug(
            f"Flushing content for {self._note}, is_string={self._is_string}"
        )

        if self._is_string:
            assert isinstance(blob, str)

            blob: bytes = blob.encode("utf-8")
            headers["Content-Type"] = "text/plain; charset=utf-8"
        else:
            assert isinstance(blob, bytes)

            headers["Content-Type"] = "application/octet-stream"
            headers["Content-Transfer-Encoding"] = "binary"

        # generated ETAPI client only supports text, so make request manually
        response = requests.put(self._url, headers=headers, data=blob)

        assert (
            response.status_code == 204
        ), f"PUT {self._url} response: {response.status_code}"

        self._backing = self._working
        self._working = BlobState()

        # TODO:
        # - refresh Note model using response via self._note._refresh_model()
        #   - updates note's last modified time
        # - sanity check to ensure digest is what we expect

    def _normalize_blob(self, blob: str | bytes | IO) -> str | bytes:
        if isinstance(blob, IOBase):
            fh = blob

            if self._is_string:
                assert (
                    "b" not in fh.mode
                ), f"Note content type is string, but file in binary mode: {self._note}"
            else:
                assert (
                    "b" in fh.mode
                ), f"Note content type is binary, but file in text mode: {self._note}"

            fh.seek(0)
            blob = fh.read()
        else:
            if self._is_string:
                assert isinstance(blob, str)
            else:
                assert isinstance(blob, bytes)

        return blob

    def _get_digest(self, blob: str | bytes) -> str:
        """
        Calculate digest of content.

        This should be kept in sync with src/services/utils.js:hashedBlobId()
        """

        # encode if string
        blob_bytes = blob.encode() if isinstance(blob, str) else blob

        # compute digest
        sha = hashlib.sha512(blob_bytes).digest()

        # encode in base64 and decode as string
        b64 = base64.b64encode(sha).decode()

        # make replacements to form "kinda" base62
        b62 = b64.replace("+", "X").replace("/", "Y")

        # return first 20 characters
        return b62[:20]

    @property
    def _url(self) -> str:
        """
        Return URL for content requests.
        """
        base_path = self._note._session._base_path
        return f"{base_path}/notes/{self._note.note_id}/content"
