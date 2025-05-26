"""
Test filesystem format for notes.
"""

from pathlib import Path

from trilium_alchemy import *

FS_DUMP_PATH = Path(__file__) / "fs-dump"


def test_export(session: Session, note: Note, tmp_path: Path):
    """
    Export a single note and verify output, also verifying overwrite.
    """

    label1 = Label(
        "label1",
        value="testvalue",
        inheritable=True,
        session=session,
        _attribute_id="abcdef_attr1",
    )
    note1 = Note(
        title="Note 1",
        parents=note,
        attributes=[label1],
        note_id="abcdef",
        session=session,
    )
    # TODO: add child note

    note1.export_fs(tmp_path)

    # TODO: compare tmp_path with FS_DUMP_PATH / "note1"
    # filecmp.dircmp
    # filecmp.cmpfiles
