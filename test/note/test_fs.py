"""
Test filesystem format for notes.
"""

from pathlib import Path

from trilium_alchemy import *

from ..conftest import compare_folders

FS_NOTES_PATH = Path(__file__).parent / "fs-dump"


def test_dump(session: Session, note: Note, tmp_path: Path):
    """
    Dump a single note and verify output, also verifying overwrite.
    """

    label1 = Label(
        "label1",
        value="testValue",
        inheritable=True,
        session=session,
        _attribute_id="abcdef_attr1",
    )
    note1 = Note(
        title="Note 1",
        parents=note,
        attributes=[label1],
        content="<p>Hello, world!</p>",
        note_id="abcdef",
        session=session,
    )
    note1 += (
        Note(title="Note 1 child", note_id="ghijkl", session=session),
        "Test prefix",
    )

    # flush so branch id gets generated
    session.flush()

    note1.dump_fs(tmp_path)

    # compare tmp_path with expected path
    expected_path = FS_NOTES_PATH / "note1"
    compare_folders(tmp_path, expected_path)
