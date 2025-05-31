"""
Test filesystem format for notes.
"""

from pathlib import Path

from trilium_alchemy import *

from ..conftest import compare_folders
from ..fs_utils import check_note_1, create_note_1

FS_NOTES_PATH = Path(__file__).parent / "fs-dump"
NOTE_1_PATH = FS_NOTES_PATH / "note_1"


def test_dump(session: Session, note: Note, tmp_path: Path):
    """
    Dump a single note and verify output, also verifying overwrite.
    """

    note_1 = create_note_1(session, note)
    note_1.dump_fs(tmp_path)

    content_txt_path = tmp_path / "content.txt"
    content_bin_path = tmp_path / "content.bin"

    # compare tmp_path with expected path
    compare_folders(tmp_path, NOTE_1_PATH)

    # change content and add binary content
    note_1.content = "Changed content"
    content_bin_path.write_bytes(b"Test bytes")

    note_1.dump_fs(tmp_path)

    # content should have been updated and binary content removed
    assert content_txt_path.read_text() == "Changed content"
    assert not content_bin_path.exists()


def test_load(session: Session, note: Note):
    """
    Load a single note and verify it.
    """

    # load and check
    note_1 = Note.load_fs(NOTE_1_PATH, session)
    check_note_1(note_1, State.CREATE)

    # add parent and create, then check again
    note_1 ^= note
    session.flush()
    check_note_1(note_1, State.CLEAN)

    # modify data
    note_1.title = "New title"
    note_1.labels.set_value("label_1", "new_value")
    note_1.relations.set_target("relation_1", session.root)
    note_1.branches.children[0].prefix = "New prefix"

    assert note_1.state is State.UPDATE
    assert len(session.dirty_map[State.UPDATE]) == 4

    # reload from folder and check again
    note_1_reload = Note.load_fs(NOTE_1_PATH, session)
    assert note_1 is note_1_reload
    assert session.dirty_count == 0
    check_note_1(note_1, State.CLEAN)
