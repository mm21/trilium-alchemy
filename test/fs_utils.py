"""
Utilities for testing filesystem dump/load-related functionality.
"""

from trilium_alchemy import *

__all__ = [
    "create_note_1",
]

NOTE_1_ID = "note_1"
NOTE_2_ID = "note_2"


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
