from pytest import mark

from trilium_alchemy import *


def test_text_empty(session: Session, note: Note):
    """
    Get content of empty note and verify empty string.
    """
    assert note._is_clean
    assert note.content == ""


def test_text(session: Session, note: Note):
    """
    Set note text content using note.content interface.
    """
    TEXT = "<p>Hello world</p>"

    note.content = TEXT

    assert note._is_update
    assert note.content == TEXT

    note.content_str = ""
    assert note.content_str == ""
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

    # should have gotten blobId from note model, not fetched content
    assert note._content._backing.digest is not None
    assert note._content._backing.blob is None

    assert note._content._working.digest is not None
    assert note.blob_id == note._content._working.digest

    note.content = TEXT
    assert note._is_clean

    # force retrieving from server
    note.invalidate()

    assert note.content == TEXT
    assert note._content._backing.blob is not None


@mark.note_type("file")
@mark.note_mime("application/octet-stream")
def test_bin(session: Session, note: Note):
    """
    Set note binary content using note.content interface.
    """
    assert note.note_type == "file"
    assert note.mime == "application/octet-stream"

    BLOB = b"Test bin"

    note.content = BLOB

    assert note._is_update
    assert note.content == BLOB

    note.content_bin = b"{BLOB}_2"
    assert note.content_bin == b"{BLOB}_2"

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
