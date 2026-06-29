from io import BytesIO
from pathlib import Path

from pytest import raises

from trilium_alchemy import Attachment, Note, Session, State

# arbitrary binary payloads; Trilium doesn't validate that they're real images
IMG1 = b"\x89PNG\r\n\x1a\n" + b"first image payload" * 4
IMG2 = b"\x89PNG\r\n\x1a\n" + b"second image payload" * 4


def test_create_flush_roundtrip(note: Note, tmp_path: Path):
    """
    Assign a file handle and a Path, flush, and verify round-trip through a fresh fetch.
    """
    img1 = _write_image(tmp_path, "a.png", IMG1)
    img2 = _write_image(tmp_path, "b.png", IMG2)

    assert note._is_clean
    assert len(note.attachments) == 0

    note.attachments = [open(img1, "rb"), img2]

    assert note.state is State.UPDATE
    assert len(note.attachments) == 2
    assert note.attachments[0].content == IMG1
    assert note.attachments[1].content == IMG2

    # title derived from filename
    assert note.attachments[0].title == "a.png"
    assert note.attachments[1].title == "b.png"

    # mime guessed from filename
    assert note.attachments[0].mime == "image/png"
    assert note.attachments[0].role == "image"

    note.flush()

    assert note._is_clean
    assert all(a._is_clean for a in note.attachments)
    assert all(a.attachment_id is not None for a in note.attachments)

    blob_ids = [a.blob_id for a in note.attachments]

    # force a fresh fetch from the server
    note.invalidate()

    assert len(note.attachments) == 2
    assert {a.content for a in note.attachments} == {IMG1, IMG2}
    assert [a.blob_id for a in note.attachments] == blob_ids


def test_clear(session: Session, note: Note, tmp_path: Path):
    """
    Removing all attachments deletes them on the server.
    """
    assert note.note_id
    img = _write_image(tmp_path, "a.png", IMG1)
    note.attachments = [img]
    note.flush()
    assert len(session.api.get_note_attachments(note.note_id)) == 1

    note.attachments = []
    assert note.state is State.UPDATE
    assert len(note.attachments) == 0

    note.flush()
    assert note._is_clean
    assert len(session.api.get_note_attachments(note.note_id)) == 0


def test_dirty_revert(note: Note, tmp_path: Path):
    """
    Adding then removing attachments before flush returns the note to clean.
    """
    img = _write_image(tmp_path, "a.png", IMG1)

    assert note._is_clean
    note.attachments = [img]
    assert note.state is State.UPDATE

    note.attachments = []
    assert note._is_clean


def test_metadata_patch(note: Note, tmp_path: Path):
    """
    Updating attachment metadata is flushed via PATCH.
    """
    img = _write_image(tmp_path, "a.png", IMG1)
    note.attachments = [img]
    note.flush()

    attachment = note.attachments[0]
    attachment.title = "renamed.png"
    assert attachment.state is State.UPDATE

    note.flush()

    note.invalidate()
    assert note.attachments[0].title == "renamed.png"
    assert note.attachments[0].content == IMG1


def test_content_update(note: Note, tmp_path: Path):
    """
    Updating attachment content is flushed via raw ETAPI.
    """
    img = _write_image(tmp_path, "a.png", IMG1)
    note.attachments = [img]
    note.flush()

    note.attachments[0].content = IMG2
    assert note.attachments[0].state is State.UPDATE

    note.flush()
    note.invalidate()

    assert note.attachments[0].content == IMG2


def test_save(note: Note, tmp_path: Path):
    """
    Attachment.save() writes content to disk.
    """
    img = _write_image(tmp_path, "a.png", IMG1)
    note.attachments = [img]
    note.flush()

    out = tmp_path / "out.png"
    note.attachments[0].save(out)
    assert out.read_bytes() == IMG1


def test_explicit_attachment_bytes(session: Session, note: Note):
    """
    Constructing an Attachment from bytes requires a title.
    """
    note.attachments = [Attachment(title="a.png", content=IMG1, session=session)]
    assert len(note.attachments) == 1
    assert note.attachments[0].title == "a.png"
    assert note.attachments[0].content == IMG1
    note.flush()
    note.invalidate()
    assert note.attachments[0].content == IMG1


def test_bytesio_with_name(note: Note):
    """
    A BytesIO with a .name is accepted and derives its title.
    """
    fh = BytesIO(IMG1)
    fh.name = "mem.png"
    note.attachments = [fh]
    assert note.attachments[0].title == "mem.png"
    assert note.attachments[0].content == IMG1


def test_invalid(session: Session, note: Note, tmp_path: Path):
    """
    Invalid inputs.
    """
    # bytes
    with raises(ValueError):
        note.attachments = [IMG1]  # type: ignore

    # bytes without title
    with raises(ValueError):
        Attachment(content=IMG1, session=session)  # type: ignore

    # non-image content
    txt = tmp_path / "doc.txt"
    txt.write_bytes(b"not an image")

    with raises(ValueError):
        note.attachments = [txt]

    with raises(ValueError):
        Attachment(content=b"x", title="doc.txt", session=session)


def test_note_init_attachments(session: Session, note: Note, tmp_path: Path):
    """
    Attachments can be passed to Note().
    """
    img1 = _write_image(tmp_path, "a.png", IMG1)
    img2 = _write_image(tmp_path, "b.png", IMG2)

    child = Note(
        title="child",
        parents=note,
        attachments=[img1, open(img2, "rb")],
        session=session,
    )

    assert len(child.attachments) == 2
    child.flush()

    child.invalidate()
    assert {a.content for a in child.attachments} == {IMG1, IMG2}


def _write_image(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path
