"""
Test basic CRUD capability of notes.
"""

import datetime
import zipfile
from pathlib import Path

from pytest import mark
from trilium_client.models.attribute import Attribute as EtapiAttributeModel
from trilium_client.models.branch import Branch as EtapiBranchModel

from trilium_alchemy import *

from ..conftest import check_read_only, create_label, note_exists


class NoteSubclass(Note):
    @property
    def label1(self) -> str:
        return self["label1"]

    @label1.setter
    def label1(self, val: str):
        self["label1"] = val


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

    # ensure exists
    assert note_exists(session.api, note.note_id)

    # create new note and populate with attributes
    note2_child = Note(session=session)
    note2 = Note(
        title="Note2",
        note_type="code",
        mime="text/css",
        parents=note,
        children=[note2_child],
        attributes=[
            Label("label1", "value1", session=session),
            Label("label1", session=session),
        ],
        content="/* Hello, world! */",
        session=session,
    )

    session.flush()

    assert note2.title == "Note2"
    assert note2.note_type == "code"
    assert note2.mime == "text/css"
    assert note2.parents[0] is note
    assert note2.children[0] is note2_child
    assert note2.labels.get_values("label1") == ["value1", ""]
    assert note2.content == "/* Hello, world! */"


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


@mark.attribute("label1", "value1")
def test_refresh(session: Session, note: Note):
    branch = note.branches.parents[0]
    label1 = note.labels.owned[0]

    assert branch.prefix == ""
    assert label1.value == "value1"

    # modify branch/label using ETAPI directly
    session.api.patch_branch_by_id(
        branch.branch_id, EtapiBranchModel(prefix="prefix2")
    )
    session.api.patch_attribute_by_id(
        label1.attribute_id, EtapiAttributeModel(value="value2")
    )

    # modify working models
    branch.prefix = "prefix1"
    label1.value = "value1-2"

    note.refresh()

    assert branch.prefix == "prefix2"
    assert label1.value == "value2"


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
    child3 = Note(title="Test child 3", session=session)

    # clone to top-level children
    child3 ^= [child1, child2]

    # add top-level children
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

    def check_copy(note_copy: Note, deep: bool):
        assert note_copy.title == "Test note"
        assert note_copy.note_type == "code"
        assert note_copy.mime == "text/css"

        assert note_copy.content == "Test CSS"

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

        assert len(note_copy.children) == 2
        child1, child2 = note_copy.children

        assert len(child1.children) == 1
        assert len(child2.children) == 1

        # ensure cloned child is preserved
        assert child1.children[0] is child2.children[0]

        if deep:
            assert branch1.child is not note.children[0]
            assert branch2.child is not note.children[1]
        else:
            assert branch1.child is note.children[0]
            assert branch2.child is note.children[1]

    # create deep copy
    copy_deep = note.copy(deep=True)

    # create shallow copy w/content
    copy_shallow = note.copy()

    # place as children of second note
    note2 += [
        copy_deep,
        copy_shallow,
    ]

    # verify
    check_copy(copy_deep, True)
    check_copy(copy_shallow, False)

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


def test_subclass(note: Note):
    """
    Verify subclass with convenience property.
    """

    note.title = "Test note"
    subclass = note.transmute(NoteSubclass)

    assert note is subclass
    assert subclass.title == "Test note"

    subclass.label1 = "value1"
    assert subclass.label1 == "value1"


def test_transmute(note1: Note, note2: Note):
    @label("testLabel")
    class DeclarativeNoteSubclass(BaseDeclarativeNote):
        pass

    def check_subclass(note: Note, subclass: Note, note_cls: type[Note]):
        assert note is subclass
        assert isinstance(note, note_cls)
        assert note.title == note_cls.__name__

    note1.title = "NoteSubclass"

    note_subclass = note1.transmute(NoteSubclass)
    decl_note_subclass = note2.transmute(DeclarativeNoteSubclass)

    check_subclass(note1, note_subclass, NoteSubclass)
    check_subclass(note2, decl_note_subclass, DeclarativeNoteSubclass)


def test_template(session: Session, note1: Note, note2: Note):
    # note cloned to template and first child of template
    @label("childLabel2", "childLabelValue2")
    class TemplateChild2(BaseDeclarativeNote):
        content_ = "Test content 2"
        singleton = True

    @label("childLabel1", "childLabelValue1")
    @children(TemplateChild2)
    class TemplateChild1(BaseDeclarativeNote):
        content_ = "Test content 1"

    @label("templateLabel")
    @children(TemplateChild1, TemplateChild2)
    class TemplateTest(BaseTemplateNote):
        content_ = "Test content"

    @relation("template", TemplateTest)
    class TemplateInstanceTest(BaseDeclarativeNote):
        pass

    # create template
    template = TemplateTest(session=session)
    template ^= note1
    session.flush()

    def check_instance(note: Note, expect_children: int = 2):
        assert note.title == "Instance"
        assert note.labels.inherited.get_value("templateLabel") == ""
        assert note.content == "Test content"
        assert "template" not in note.labels
        assert "template" in note.relations

        assert len(note.children) == expect_children
        child1, child2 = note.children[:2]

        assert child1.title == "TemplateChild1"
        assert child1["childLabel1"] == "childLabelValue1"
        assert child1.content == "Test content 1"
        assert len(child1.children) == 1
        assert child1.children[0] is child2

        assert child2.title == "TemplateChild2"
        assert child2["childLabel2"] == "childLabelValue2"
        assert child2.content == "Test content 2"
        assert len(child2.children) == 0

    # create with template
    inst1 = Note(
        title="Instance", session=session, parents=note2, template=template
    )

    # explicitly add ~template
    inst2 = Note(title="Instance", session=session, parents=note2)
    inst2.relations.append_target("template", template)

    # declaratively added template
    inst3 = TemplateInstanceTest(
        title="Instance", parents=note2, session=session
    )

    session.flush()

    # refresh to get inherited attributes
    inst1.refresh()
    inst2.refresh()
    inst3.refresh()

    check_instance(inst1)
    check_instance(inst2)
    check_instance(inst3)

    # modify instances and ensure they get re-synced

    del inst1.children[0]
    del inst2.children[1]
    inst3.children = [inst3.children[1], inst3.children[0]]

    session.flush()

    inst1.sync_template(template)
    inst2.sync_template(template)
    inst3.sync_template(template)

    check_instance(inst1)
    check_instance(inst2)
    check_instance(inst3)

    del inst1.children[0].children[0]
    inst1.children[1].content = ""

    session.flush()

    inst1.sync_template(template)
    check_instance(inst1)

    inst1.children.insert(1, Note(title="Test child 3", session=session))
    assert inst1.children[1].title == "Test child 3"

    session.flush()

    inst1.sync_template(template)
    check_instance(inst1, expect_children=3)

    assert inst1.children[2].title == "Test child 3"


def test_cleanup_positions(session: Session, note: Note):
    """
    Set inconsistent positions and test cleaning them up to intervals of 10.
    """

    # create attributes directly
    create_label(session.api, note, "label1", "value1", 1)
    create_label(session.api, note, "label2", "value2", 3)
    create_label(session.api, note, "label3", "value3", 10)

    note.refresh()
    assert len(note.labels.owned) == 3
    assert session.dirty_count == 0

    label1, label2, label3 = note.labels.owned

    assert label1.position == 1
    assert label2.position == 3
    assert label3.position == 10

    note._cleanup_positions()
    assert session.dirty_count == 3

    assert label1.position == 10
    assert label2.position == 20
    assert label3.position == 30

    session.flush()
    assert session.dirty_count == 0
