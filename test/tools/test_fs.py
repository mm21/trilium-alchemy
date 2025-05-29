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
    dump_notes([note_1], tmp_path, recursive=True, prune=True)

    # compare tmp_path with expected path
    compare_folders(tmp_path, FS_NOTES_PATH)
