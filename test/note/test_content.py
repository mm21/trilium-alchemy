from pytest import mark

from trilium_alchemy import *


"""
Get content of empty note and verify empty string.
"""


def test_text_empty(session: Session, note: Note):
    assert note._is_clean
    assert note.content == ""


"""
Set note text content using note.content interface.
"""


def test_text(session: Session, note: Note):
    TEXT = "<p>Hello world</p>"

    note.content = TEXT

    assert note._is_update
    assert note.content == TEXT

    note.content = ""
    assert note.content == ""
    assert note._is_clean

    note.content = TEXT
    assert note._is_update

    note.flush()

    assert note._is_clean
    assert note.content == TEXT

    note.invalidate()

    # test determination of dirty content based on digest

    note.content = f"{TEXT}_2"
    assert note._is_update

    if note._content._backing.digest:
        # if we have blobId, we shouldn't have fetched the content
        assert note._content._backing.blob is None
    else:
        # if we don't have blobId, we should have fetched the content to compare
        assert note._content._backing.blob is not None

    note.content = TEXT
    assert note._is_clean

    # force retrieving from server
    note.invalidate()

    assert note.content == TEXT
    assert note._content._backing.blob is not None


"""
Set note binary content using note.content interface.
"""


@mark.note_type("file")
@mark.note_mime("application/octet-stream")
def test_bin(session: Session, note: Note):
    assert note.note_type == "file"
    assert note.mime == "application/octet-stream"

    BLOB = b"Test bin"

    note.content = BLOB

    assert note._is_update
    assert note.content == BLOB

    note.content = b"{BLOB}_2"
    assert note.content == b"{BLOB}_2"

    note.content = BLOB
    note.flush()

    assert note._is_clean
    assert note.content == BLOB

    # force retrieving from server
    note.invalidate()

    assert note.content == BLOB


TEXT_FILE_CONTENT = "<p>Test content</p>"


@mark.temp_file(TEXT_FILE_CONTENT)
def test_text_file(session: Session, note: Note, temp_file: str):
    note.content = open(temp_file)
    assert note.content == TEXT_FILE_CONTENT

    note.flush()
    note.invalidate()

    assert note.content == TEXT_FILE_CONTENT


BIN_FILE_CONTENT = b"Test content"


@mark.temp_file(BIN_FILE_CONTENT)
@mark.note_type("file")
@mark.note_mime("application/octet-stream")
def test_bin_file(session: Session, note: Note, temp_file: str):
    note.content = open(temp_file, "rb")
    assert note.content == BIN_FILE_CONTENT

    note.flush()
    note.invalidate()

    assert note.content == BIN_FILE_CONTENT
