"""
Test filesystem dump/load tool functionality.
"""

from pathlib import Path

from trilium_alchemy import *

# from trilium_alchemy.tools.fs import dump_notes

# from ..conftest import compare_folders


def test_dump(session: Session, note: Note, tmp_path: Path):
    """
    Dump note hierarchy to folder.
    """
