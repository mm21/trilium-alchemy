from pytest import raises

from trilium_alchemy import *

"""
TODO: move sorter testing from test_note.py::test_flush_dependency here

- note1 (deleted)
    - note2 (unchanged)
        - note3 (changed)

* flush
* observe error: note3 attempted to be updated, but deleted
* gracefully handle error
"""


def test_validation(session: Session):
    # create note with no parent
    note = Note(session=session)

    with raises(ValidationError):
        note.flush()
