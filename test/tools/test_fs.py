"""
Test filesystem dump/load tool functionality.
"""

from pathlib import Path

from trilium_alchemy import *
from trilium_alchemy.tools.fs import dump_notes

from ..conftest import compare_folders
from ..fs_utils import create_note_1

FS_NOTES_PATH = Path(__file__).parent / "fs-dump"


def test_dump(session: Session, note: Note, tmp_path: Path):
    """
    Dump note hierarchy to folder.
    """

    note_1 = create_note_1(session, note)
    dump_notes([note_1], tmp_path, recursive=True)

    # compare tmp_path with expected path
    compare_folders(tmp_path, FS_NOTES_PATH)

    # add unexpected folders and file
    unexpected_folder = tmp_path / "unexpected-folder"
    unexpected_pruned_folder = tmp_path / "ab"  # should get pruned
    unexpected_file = tmp_path / "unexpected-file.txt"

    unexpected_folder.mkdir()
    unexpected_pruned_folder.mkdir()
    unexpected_file.write_text("")

    # dump with pruning
    dump_notes([note_1], tmp_path, recursive=True, prune=True)

    assert unexpected_folder.exists()
    assert not unexpected_pruned_folder.exists()
    assert unexpected_file.exists()

    # remove unexpected folder/file and compare again
    unexpected_folder.rmdir()
    unexpected_file.unlink()
    compare_folders(tmp_path, FS_NOTES_PATH)
