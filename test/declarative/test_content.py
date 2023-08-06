from pytest import mark, fixture

from trilium_alchemy import *


class MyTextNote(Note):
    content_file = "files/test.html"


class MyBinNote(Note):
    note_type = "file"
    mime = "application/octet-stream"
    content_file = "files/test.bin"


TEST_CONTENT = "<p>Test</p>"


# set content directly without file
class NoFile(Note):
    content = TEST_CONTENT


def test_text(session: Session, note: Note):
    note_test = MyTextNote(parents={note}, session=session)

    assert note_test._is_create
    assert note_test.note_type == "text"
    assert note_test.mime == "text/html"
    assert note_test.content == "<p>Test content</p>"

    note_test.flush()
    note_test.invalidate()

    assert note_test._is_clean
    assert note_test.content == "<p>Test content</p>"

    # check originalFilename attribute
    assert len(note_test.attributes["originalFilename"]) == 1
    assert note_test["originalFilename"] == "test.html"


def test_bin(session: Session, note: Note):
    note_test = MyBinNote(parents={note}, session=session)

    assert note_test._is_create
    assert note_test.note_type == "file"
    assert note_test.mime == "application/octet-stream"
    assert note_test.content == b"Test content"

    note_test.flush()
    note_test.invalidate()

    assert note_test._is_clean
    assert note_test.content == b"Test content"


def test_nofile(session: Session, note: Note):
    note_test = NoFile(parents={note}, session=session)
    assert note_test.content == TEST_CONTENT
    assert "originalFilename" not in note_test.attributes
