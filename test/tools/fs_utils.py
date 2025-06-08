"""
Utilities for testing filesystem dump/load-related functionality.
"""

from pathlib import Path

from trilium_alchemy import *

__all__ = [
    "NOTE_1_ID",
    "NOTE_1_BLOB_ID",
    "NOTE_2_ID",
    "NOTE_2_BLOB_ID",
    "FS_DUMPS_PATH",
    "NOTE_1_DUMP_PATH",
    "TREE_DUMP_PATH",
    "create_note_1",
    "check_note_1",
]

NOTE_1_ID = "note_1"
NOTE_1_BLOB_ID = "7XJSwh6apxkriWy2bX9P"

NOTE_2_ID = "note_2"
NOTE_2_BLOB_ID = "zEin5JG8PQ4s4EMeDl5p"


FS_DUMPS_PATH = Path(__file__).parent / "fs-dumps"
NOTE_1_DUMP_PATH = FS_DUMPS_PATH / "note-1"
TREE_DUMP_PATH = FS_DUMPS_PATH / "tree"


def create_note_1(session: Session, parent: Note) -> Note:
    """
    Create note1 tree with specific note ids.
    """

    note_1 = Note(
        title="Note 1",
        parents=parent,
        content="<p>Hello, world 1!</p>",
        note_id=NOTE_1_ID,
        session=session,
    )
    note_2 = Note(
        title="Note 2",
        content="<p>Hello, world 2!</p>",
        note_id=NOTE_2_ID,
        session=session,
    )
    attr_1 = Label(
        "label_1",
        value="test_value",
        inheritable=True,
        session=session,
    )
    attr_2 = Relation(
        "relation_1",
        target=note_2,
        session=session,
    )

    note_1 += [attr_1, attr_2, (note_2, "Test prefix")]

    # flush so branch id gets generated
    session.flush()

    return note_1


def check_note_1(note: Note, state: State):
    """
    Verify note 1.
    """
    assert note.state is state
    assert note.note_id == NOTE_1_ID
    assert note.title == "Note 1"
    assert note.note_type == "text"
    assert note.mime == "text/html"
    assert len(note.attributes.owned) == 2
    assert len(note.children) == 1
    assert note.blob_id == NOTE_1_BLOB_ID

    label_1, relation_1 = note.attributes.owned
    note_2 = note.children[0]

    assert isinstance(label_1, Label)
    assert label_1.state is state
    assert label_1.name == "label_1"
    assert label_1.value == "test_value"
    assert label_1.inheritable is True

    assert isinstance(relation_1, Relation)
    assert relation_1.state is state
    assert relation_1.name == "relation_1"
    assert relation_1.target is note_2
    assert relation_1.inheritable is False

    child_branch = note.branches.lookup_branch(note_2)
    assert child_branch
    assert child_branch.state is state
    assert child_branch.prefix == "Test prefix"
