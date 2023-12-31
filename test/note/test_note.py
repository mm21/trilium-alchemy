from pytest import mark

from trilium_alchemy import *

from ..conftest import check_read_only, note_exists

import datetime

"""
Test basic CRUD capability of notes.
"""

# TODO: test_lazy_read: when instantiated by id, ensure model not loaded until
# accessed


# Create new note as a child of provided note
def test_create(session: Session, note: Note):
    parent = note

    # generate title based on timestamp
    now = str(datetime.datetime.now())
    title = f"Test title {now}"

    note = Note(title=title, session=session, parents={parent})
    assert note.note_id is None

    assert note.title == title
    assert note._model._exists is False
    assert note.date_created is None
    assert note.date_modified is None
    assert note.utc_date_created is None
    assert note.utc_date_modified is None

    note.flush()

    assert note.note_id is not None

    assert note._model._exists is True
    assert note.date_created is not None
    assert note.date_modified is not None
    assert note.utc_date_created is not None
    assert note.utc_date_modified is not None

    print(f"Created note: {note}")

    # ensure exists
    assert note_exists(session.api, note.note_id)

    # newly created note will be deleted when parent cleaned up


def test_update(session: Session, note: Note):
    assert note._is_clean

    date_modified_before = note.date_modified

    # get current title
    title = note.title

    # change title and ensure dirty
    note.title = "Title 2"
    assert note._is_dirty

    # change title to original and ensure clean
    note.title = title
    assert note._is_clean

    # do the same for type, mime

    note.note_type = "code"
    assert note._is_dirty

    note.note_type = "text"
    assert note._is_clean

    note.mime = "text/plain"
    assert note._is_dirty

    note.mime = "text/html"
    assert note._is_clean

    # ensure can't write read-only fields
    check_read_only(
        note,
        [
            "note_id",
            "is_protected",
            "date_created",
            "date_modified",
            "utc_date_created",
            "utc_date_modified",
        ],
    )

    # change params back and ensure dirty again
    note.title = "Title 2"
    note.note_type = "code"
    note.mime = "text/plain"
    assert note._is_dirty

    # flush change and ensure clean
    note.flush()
    assert note._is_clean

    assert note.title == "Title 2"
    assert note.note_type == "code"
    assert note.mime == "text/plain"

    date_modified_after = note.date_modified

    assert date_modified_after > date_modified_before


# inform note fixture to skip cleaning up note, will delete in test case
@mark.skip_teardown
def test_delete(session: Session, note: Note):
    assert note._is_clean

    note.delete()
    assert note._is_delete

    note.flush()
    assert note._is_clean

    assert not note_exists(session.api, note.note_id)


# modify attributes/branches and ensure they get flushed when note is flushed
def test_flush(session: Session, note1: Note, note2: Note, branch: Branch):
    # make note and attributes/branches dirty
    note1.title = "title2"
    note1.attributes["label1"] = ""
    branch.prefix = "prefix2"

    parent_branch = list(note1.branches.parents)[0]
    parent_branch.prefix = "prefix2"

    note2.attributes["label1"] = ""

    assert session.dirty_count == 5

    # flush note1 and its label1
    note1.flush()

    assert session.dirty_count == 3
    assert note2.attributes["label1"][0]._is_dirty

    note2.flush()

    assert session.dirty_count == 2
    assert note2.attributes["label1"][0]._is_clean

    branch.flush()
    parent_branch.flush()
    assert session.dirty_count == 0


# Build note tree to ensure dependencies are handled correctly when flushing
def test_flush_dependency(session: Session, note: Note):
    note2 = Note(session=session)
    note3 = Note(session=session)
    note4 = Note(session=session)

    note += note2
    note2 += note3
    note3 += note4

    # add a relation with target as note4
    note["relation1"] = note4

    # should trigger flush of whole tree as relation depends on target
    note.attributes["relation1"][0].flush()

    assert note._is_clean
    assert note2._is_clean
    assert note3._is_clean
    assert note4._is_clean

    # change a note and delete an ancestor, deleting it implicitly
    note4.title = "Expected warning"

    # create a new label
    note4["expectedWarning"] = ""

    note2.delete()
    note2.flush()

    # will generate warnings, but not crash
    session.flush()


# Create a simple hierarchy and then abandon the root note before it's created
# (should get warnings, but no crash)
def test_flush_orphan(session: Session):
    note = Note(parents=session.root, session=session)
    note.branches.parents[0].prefix = "Expected warning"
    note += Label("expectedWarning", session=session)
    note += Note(title="Expected warning", session=session)
    note.children[0] += Label("expectedWarning2", session=session)
    note.branches.children[0].prefix = "Expected warning"

    note.delete()

    session.flush()


def test_lazy(session: Session, note1: Note, note2: Note, branch: Branch):
    assert not note1._model._setup_done
    assert not note2._model._setup_done
    assert not branch._model._setup_done

    # read title to fetch model
    title = note1.title
    assert note1._model._setup_done
    assert branch._model._setup_done

    # shouldn't have fetched note2 since it wasn't accessed
    assert not note2._model._setup_done

    title = branch.child.title
    assert note2._model._setup_done
