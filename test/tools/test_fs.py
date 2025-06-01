"""
Test filesystem dump/load functionality.
"""

from pathlib import Path

from trilium_alchemy import *
from trilium_alchemy.tools.fs.note import dump_note, load_note
from trilium_alchemy.tools.fs.tree import dump_tree, load_tree

from ..conftest import compare_folders
from ..fs_utils import NOTE_1_ID, check_note_1, create_note_1

FS_DUMPS_PATH = Path(__file__).parent / "fs-dumps"

NOTE_1_DUMP_PATH = FS_DUMPS_PATH / "note-1"
TREE_DUMP_PATH = FS_DUMPS_PATH / "tree"


def test_dump_note(session: Session, note: Note, tmp_path: Path):
    """
    Dump a single note and verify output, also verifying overwrite.
    """

    content_txt_path = tmp_path / "content.txt"
    content_bin_path = tmp_path / "content.bin"

    note_1 = create_note_1(session, note)

    dump_note(tmp_path, note_1)
    compare_folders(tmp_path, NOTE_1_DUMP_PATH)

    # change note content and add binary content
    note_1.content = "Changed content"
    content_bin_path.write_bytes(b"Test bytes")

    dump_note(tmp_path, note_1)

    # content should have been updated and binary content removed
    assert content_txt_path.read_text() == "Changed content"
    assert not content_bin_path.exists()

    # change dump content without updating metadata
    content_txt_path.write_text("Changed content 2")

    # dump without checking content hash
    dump_note(tmp_path, note_1)
    assert content_txt_path.read_text() == "Changed content 2"

    # dump and check content hash to update content
    dump_note(tmp_path, note_1, check_content_hash=True)
    assert content_txt_path.read_text() == "Changed content"


def test_load_note(session: Session, note: Note):
    """
    Load a single note and verify it.
    """

    # load and check
    note_1 = load_note(NOTE_1_DUMP_PATH, session)
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
    note_1_reload = load_note(NOTE_1_DUMP_PATH, session)
    assert note_1 is note_1_reload
    assert session.dirty_count == 0
    check_note_1(note_1, State.CLEAN)


def test_dump_tree(session: Session, note: Note, tmp_path: Path):
    """
    Dump note hierarchy to folder.
    """

    note_1 = create_note_1(session, note)
    dump_tree(tmp_path, [note_1], recursive=True, prune=False)

    # compare tmp_path with expected path
    compare_folders(tmp_path, TREE_DUMP_PATH)

    # add unexpected folders and file
    unexpected_folder = tmp_path / "unexpected-folder"
    unexpected_pruned_folder = tmp_path / "ab"  # should get pruned
    unexpected_file = tmp_path / "unexpected-file.txt"

    unexpected_folder.mkdir()
    unexpected_pruned_folder.mkdir()
    unexpected_file.write_text("")

    # dump with pruning
    dump_tree(tmp_path, [note_1], recursive=True, prune=True)

    assert unexpected_folder.exists()
    assert not unexpected_pruned_folder.exists()
    assert unexpected_file.exists()

    # remove unexpected folder/file and compare again
    unexpected_folder.rmdir()
    unexpected_file.unlink()
    compare_folders(tmp_path, TREE_DUMP_PATH)


def test_load_tree(session: Session, note: Note):
    """
    Load note hierarchy from folder.
    """

    notes = load_tree(TREE_DUMP_PATH, session, parent_note=note)

    # find and check note 1
    note_1 = next(n for n in notes if n.note_id == NOTE_1_ID)
    check_note_1(note_1, State.CREATE)

    assert len(note.children)
    assert note.children[0] is note_1
