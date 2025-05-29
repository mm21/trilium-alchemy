"""
Test filesystem format for notes.
"""

from pathlib import Path

from trilium_alchemy import *

from ..conftest import compare_folders
from ..fs_utils import create_note_1

FS_NOTES_PATH = Path(__file__).parent / "fs-dump"


def test_dump(session: Session, note: Note, tmp_path: Path):
    """
    Dump a single note and verify output, also verifying overwrite.
    """

    note_1 = create_note_1(session, note)
    note_1.dump_fs(tmp_path)

    # compare tmp_path with expected path
    compare_folders(tmp_path, FS_NOTES_PATH / "note_1")
