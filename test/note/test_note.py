"""
Test basic CRUD capability of notes.
"""

import datetime
import zipfile
from pathlib import Path

from pytest import mark

from trilium_alchemy import *

from ..conftest import check_read_only, note_exists


def test_create(session: Session, note: Note):
    """
    Create new note as a child of provided note.
    """

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


def test_flush(session: Session, note1: Note, note2: Note, branch: Branch):
    """
    Modify attributes/branches and ensure they get flushed when note is
    flushed.
    """

    # make note and attributes/branches dirty
    note1.title = "title2"
    note1["label1"] = ""
    branch.prefix = "prefix2"

    parent_branch = list(note1.branches.parents)[0]
    parent_branch.prefix = "prefix2"

    note2["label1"] = ""

    assert session.dirty_count == 5

    # flush note1 and its label1
    note1.flush()

    assert session.dirty_count == 3
    assert note2.attributes.get("label1")._is_dirty

    note2.flush()

    assert session.dirty_count == 2
    assert note2.attributes.get("label1")._is_clean

    branch.flush()
    parent_branch.flush()
    assert session.dirty_count == 0


def test_flush_dependency(session: Session, note: Note):
    """
    Build note tree and ensure dependencies are handled correctly when
    flushing.
    """

    note2 = Note(session=session)
    note3 = Note(session=session)
    note4 = Note(session=session)

    note += note2
    note2 += note3
    note3 += note4

    # add a relation with target as note4
    note += Relation("relation1", note4, session=session)

    # should trigger flush of whole tree as relation depends on target
    note.attributes.get("relation1").flush()

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


def test_flush_orphan(session: Session):
    """
    Create a simple hierarchy and then abandon the root note before it's
    created; should get warnings, but no crash.
    """

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
    note1.title
    assert note1._model._setup_done
    assert branch._model._setup_done

    # shouldn't have fetched note2 since it wasn't accessed
    assert not note2._model._setup_done

    branch.child.title
    assert note2._model._setup_done


def test_paths(session: Session):
    """
    Verify API to get note paths.
    """

    a, b1, b2, c, d = [
        Note(title=f"Note{i}", session=session) for i in range(5)
    ]

    a += [b1, b2]
    c.parents += [b1, b2]
    c += d

    d_paths = d.paths
    assert d_paths == [
        [a, b1, c, d],
        [a, b2, c, d],
    ]
    assert d.paths_str == [
        "Note0 > Note1 > Note3 > Note4",
        "Note0 > Note2 > Note3 > Note4",
    ]


@mark.note_title("Test note")
@mark.note_type("code")
@mark.note_mime("text/css")
@mark.attribute("label1", "value1")
@mark.attribute("relation1", "root", type="relation")
def test_copy(session: Session, note: Note, note2: Note):
    # add content
    note.content = "Test CSS"

    child1 = Note(title="Test child 1", session=session)
    child2 = Note(title="Test child 2", session=session)

    # add children
    note += [
        Branch(
            child=child1,
            prefix="Test prefix",
            session=session,
        ),
        Branch(
            child=child2,
            session=session,
        ),
    ]

    session.flush()

    def check_copy(note_copy: Note, deep: bool, content: bool):
        assert note_copy.title == "Test note"
        assert note_copy.note_type == "code"
        assert note_copy.mime == "text/css"

        if content:
            assert note_copy.content == "Test CSS"
        else:
            assert note_copy.content == ""

        assert len(note_copy.attributes.owned) == 2

        # check attributes
        label1, relation1 = note_copy.attributes.owned

        assert isinstance(label1, Label)
        assert label1.name == "label1"
        assert label1.value == "value1"

        assert isinstance(relation1, Relation)
        assert relation1.name == "relation1"
        assert relation1.target is session.root

        # check children
        assert len(note_copy.branches.children) == 2
        branch1, branch2 = note_copy.branches.children

        assert branch1.prefix == "Test prefix"
        assert branch1.parent is note_copy

        assert branch2.prefix == ""
        assert branch2.parent is note_copy

        if deep:
            assert branch1.child is not note.children[0]
            assert branch2.child is not note.children[1]
        else:
            assert branch1.child is note.children[0]
            assert branch2.child is note.children[1]

    # create deep copy
    copy_deep = note.copy(deep=True)

    # create shallow copy w/content
    copy_shallow = note.copy(content=True)

    # place as children of second note
    note2 += [
        copy_deep,
        copy_shallow,
    ]

    # verify
    check_copy(copy_deep, True, False)
    check_copy(copy_shallow, False, True)

    session.flush()


@mark.note_title("Test note")
@mark.attribute("label1")
def test_export_import(note: Note, tmp_path: Path):
    """
    Verify export and import for both html and markdown.
    """

    CONTENT = "<p>Hello, world!</p>"

    note.content = CONTENT
    note.flush()

    def check_note(note: Note):
        assert note.title == "Test note"
        assert note["label1"] == ""
        assert CONTENT in note.content

    def export_import(export_format: str, child_count: int):
        export_tmp_path = tmp_path / export_format
        export_tmp_path.mkdir(parents=True, exist_ok=True)

        zip_path = export_tmp_path / "export.zip"

        # sanity check
        check_note(note)

        # invoke export API
        note.export_zip(zip_path, export_format=export_format)

        # verify export
        with zipfile.ZipFile(zip_path, "r") as file:
            file.extractall(export_tmp_path)

        extension = "html" if export_format == "html" else "md"

        meta_json = export_tmp_path / "!!!meta.json"
        note_content = export_tmp_path / f"{note.title}.{extension}"

        assert meta_json.is_file()
        assert note_content.is_file()

        # invoke import API
        child = note.import_zip(zip_path)

        # exported note should have been added as the last child
        assert len(note.children) == child_count + 1
        assert note.children[-1] is child

        check_note(child)

    formats = [
        "html",
        "markdown",
    ]

    for i, export_format in enumerate(formats):
        export_import(export_format, i)
