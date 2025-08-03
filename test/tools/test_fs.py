"""
Test filesystem dump/load functionality.
"""

from pathlib import Path

from pytest import FixtureRequest

from trilium_alchemy import *
from trilium_alchemy.tools.fs.note import dump_note, load_note
from trilium_alchemy.tools.fs.tree import (
    DumpStats,
    _map_note_dir,
    dump_tree,
    load_tree,
    scan_content,
)

from ..conftest import compare_folders
from .fs_utils import (
    NOTE_1_DUMP_PATH,
    NOTE_1_ID,
    TREE_DUMP_PATH,
    check_note_1,
    create_note_1,
    teardown_note_1,
)


def test_dump_note(
    request: FixtureRequest, session: Session, note: Note, tmp_path: Path
):
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

    teardown_note_1(request, session)


def test_load_note(request: FixtureRequest, session: Session, note: Note):
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

    teardown_note_1(request, session)


def test_dump_tree(
    request: FixtureRequest, session: Session, note: Note, tmp_path: Path
):
    """
    Dump note hierarchy to folder.
    """

    def print_stats(stats: DumpStats):
        print(f"Tree dump stats: {stats}")

    note_1 = create_note_1(session, note)

    # dump with dry run
    stats = dump_tree(tmp_path, [note_1], dry_run=True)
    assert stats.note_count == 2
    assert stats.update_count == 2
    assert stats.prune_count == 0

    # initial dump
    stats = dump_tree(tmp_path, [note_1], recurse=True, prune=False)

    print_stats(stats)
    assert stats.note_count == 2
    assert stats.update_count == 2
    assert stats.prune_count == 0

    # compare tmp_path with expected path
    compare_folders(tmp_path, TREE_DUMP_PATH)

    # add unexpected folders and file
    unexpected_folder = tmp_path / "unexpected-folder"
    unexpected_pruned_folder = tmp_path / "ab"  # should get pruned
    unexpected_file = tmp_path / "unexpected-file.txt"

    unexpected_folder.mkdir()
    unexpected_pruned_folder.mkdir()
    unexpected_file.write_text("")

    # dump with dry run
    stats = dump_tree(tmp_path, [note_1], dry_run=True)
    assert stats.note_count == 2
    assert stats.update_count == 0
    assert stats.prune_count == 1

    # dump with pruning
    stats = dump_tree(tmp_path, [note_1])

    print_stats(stats)
    assert stats.note_count == 2
    assert stats.update_count == 0
    assert stats.prune_count == 1

    assert unexpected_folder.exists()
    assert not unexpected_pruned_folder.exists()
    assert unexpected_file.exists()

    # remove unexpected folder/file and compare again
    unexpected_folder.rmdir()
    unexpected_file.unlink()
    compare_folders(tmp_path, TREE_DUMP_PATH)

    note_1_path = _map_note_dir(note_1)
    content_file = tmp_path / note_1_path / "content.txt"

    orig_content = content_file.read_text()
    updated_content = "Updated content"

    # manually modify content for note 1
    content_file.write_text(updated_content)

    # dump again, content should not be updated since the metadata wasn't updated
    stats = dump_tree(tmp_path, [note_1], recurse=False, prune=False)
    assert stats.note_count == 1
    assert stats.update_count == 0
    assert stats.prune_count == 0
    assert content_file.read_text() == updated_content

    # scan content to update metadata
    scan_content(tmp_path)

    # dump again, content should be updated
    stats = dump_tree(tmp_path, [note_1], recurse=False, prune=False)
    assert stats.note_count == 1
    assert stats.update_count == 1
    assert stats.prune_count == 0
    assert content_file.read_text() == orig_content

    teardown_note_1(request, session)


def test_load_tree(request: FixtureRequest, session: Session, note: Note):
    """
    Load note hierarchy from folder.
    """

    notes = load_tree(TREE_DUMP_PATH, session, parent_note=note)

    # find and check note 1
    note_1 = next(n for n in notes if n.note_id == NOTE_1_ID)
    check_note_1(note_1, State.CREATE)

    assert len(note.children)
    assert note.children[0] is note_1

    teardown_note_1(request, session)
