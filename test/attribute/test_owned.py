"""
Test basic CRUD capability of owned attributes.
"""

from pytest import mark

from trilium_alchemy import *

from ..conftest import attribute_exists, check_read_only


@mark.label("label1", "value1")
def test_label_update(session: Session, label: Label):
    """
    Update existing label.
    """
    assert label._is_clean

    label.value = "value2"
    assert label._is_dirty
    assert label.value == "value2"

    label.value = "value1"
    assert label._is_clean

    attribute_update(label)

    label.value = "value2"
    label._position = 20
    assert label._is_dirty

    label.flush()
    assert label._is_clean

    label.invalidate()
    assert label.value == "value2"
    assert label.position == 20


@mark.label("label1", "value1")
def test_label_update_inheritable(label: Label):
    """
    Update isInheritable for existing label.
    """
    _test_attribute_update_inheritable(label)


@mark.relation("relation1", "root")
def test_relation_update(session: Session, note: Note, relation: Relation):
    """
    Update existing relation.
    """
    assert relation._is_clean

    assert relation.target is not None
    assert relation._model.get_field("value") == "root"

    # change target to note which owns this relation
    relation.target = note
    assert relation._is_dirty

    # change target back to root
    relation.target = Note(note_id="root", session=session)
    assert relation._is_clean

    attribute_update(relation)

    relation.target = note
    relation._position = 20
    assert relation._is_dirty

    relation.flush()
    assert relation._is_clean

    relation.invalidate()
    assert relation.target is note
    assert relation.position == 20


@mark.relation("relation1", "root")
def test_relation_update_inheritable(relation: Relation):
    """
    Update isInheritable for existing relation.
    """
    _test_attribute_update_inheritable(relation)


@mark.relation("relation1", "root")
def test_relation_update_target_new(session: Session, relation: Relation):
    """
    Update relation target to a new Note which doesn't have a note_id yet.
    """

    assert relation._is_clean

    root = Note(note_id="root", session=session)

    # create new note to be target
    note_new = Note(parents=root, session=session)

    assert note_new._is_dirty
    assert note_new.note_id is None

    relation.target = note_new
    assert relation._is_dirty

    # value (target note id) should be None as target has no note_id
    assert not relation._model.get_field("value")

    relation.target = root
    assert relation._is_clean

    relation.target = note_new
    assert relation._is_dirty

    note_new.flush()
    relation.flush()

    assert note_new._is_clean
    assert relation._is_clean

    assert relation.target is note_new
    assert note_new.note_id is not None
    assert relation._model.get_field("value") == note_new.note_id

    # cleanup
    note_new.delete()
    note_new.flush()


@mark.label("label1", "value1")
def test_label_delete(session: Session, label: Label):
    """
    Delete existing label.
    """
    assert label._is_clean

    label.delete()
    assert label._is_delete

    label.flush()
    assert label._is_clean

    assert attribute_exists(session.api, label.attribute_id) is False


@mark.relation("relation1", "root")
def test_relation_delete(session: Session, relation: Relation):
    """
    Delete existing relation.
    """
    assert relation._is_clean

    relation.delete()
    assert relation._is_delete

    relation.flush()
    assert relation._is_clean

    assert attribute_exists(session.api, relation.attribute_id) is False


def test_list_create(session: Session, note: Note):
    """
    Create new label/relation and add to list.
    """
    assert len(note.attributes.owned) == 0

    # set relation target to root
    root = Note(note_id="root", session=session)

    # create attributes
    label = Label("label1", "value1", session=session)
    relation = Relation("relation1", root, session=session)

    # add attributes
    note += [label, relation]

    assert label._is_create
    assert label.note is note
    assert label.position == 10

    assert relation._is_create
    assert relation.note is note
    assert relation.position == 20

    assert len(note.attributes.owned) == 2

    label.flush()
    relation.flush()

    # clear local data
    note.invalidate()
    label.invalidate()
    relation.invalidate()

    # get attributes, fetching from server
    assert len(note.attributes.owned) == 2
    assert note.attributes.owned[0] is label
    assert note.attributes.owned[1] is relation

    assert label.name == "label1"
    assert label.value == "value1"
    assert relation.name == "relation1"
    assert relation.target is root


@mark.attribute("label1", "value1")
@mark.attribute("relation1", "root", type="relation")
def test_list_insert(session: Session, note: Note):
    """
    Insert new label as first attribute of note containing existing label/relation.
    """
    assert len(note.attributes.owned) == 2

    label1 = note.attributes.owned[0]
    relation1 = note.attributes.owned[1]

    label2 = Label("label2", session=session)

    note.attributes.owned.insert(0, label2)
    assert len(note.attributes.owned) == 3

    assert label2.position == 10
    assert label1.position == 20
    assert relation1.position == 30

    assert note.attributes.owned[0] is label2
    assert note.attributes.owned[1] is label1
    assert note.attributes.owned[2] is relation1

    assert label1._is_update
    assert label2._is_create
    assert relation1._is_update

    session.flush()

    assert label1._is_clean
    assert label2._is_clean
    assert relation1._is_clean

    note.invalidate()

    assert len(note.attributes.owned) == 3

    assert note.attributes.owned[0] is label2
    assert note.attributes.owned[1] is label1
    assert note.attributes.owned[2] is relation1


@mark.attribute("label1", "value1")
@mark.attribute("relation1", "root", type="relation")
def test_list_update(session: Session, note: Note):
    """
    Update existing label/relation.
    """
    assert len(note.attributes.owned) == 2

    label = note.attributes.owned[0]
    assert label._is_clean

    relation = note.attributes.owned[1]
    assert relation._is_clean

    label_modified_before = label.utc_date_modified
    relation_modified_before = relation.utc_date_modified

    label.value = "value2"
    assert label._is_update

    relation.target = note
    assert relation._is_update

    session.flush()

    assert label._is_clean
    assert relation._is_clean

    assert label.value == "value2"
    assert relation.target is note

    label_modified_after = label.utc_date_modified
    relation_modified_after = relation.utc_date_modified

    assert label_modified_after > label_modified_before
    assert relation_modified_after > relation_modified_before


@mark.attribute("label1")
@mark.attribute("relation1", "root", type="relation")
def test_list_delete(session: Session, note: Note):
    """
    Delete existing label/relation.
    """
    assert len(note.attributes.owned) == 2
    label = note.attributes.owned[0]
    relation = note.attributes.owned[1]

    assert label._is_clean
    assert relation._is_clean

    del note.attributes.owned[0]

    assert label._is_delete

    assert relation._is_clean
    assert relation.position == 20

    del note.attributes.owned[0]
    assert relation._is_delete

    session.flush()

    assert label._is_clean
    assert relation._is_clean


# Common routine to check update of position and read-only fields of
# label/relation.
def attribute_update(attr: BaseAttribute):
    assert attr._is_clean

    attr._position = 20
    assert attr._is_dirty
    assert attr.position == 20

    attr._position = 10
    assert attr._is_clean
    assert attr.position == 10

    # ensure can't write read-only fields
    check_read_only(
        attr,
        [
            "attribute_id",
            "utc_date_modified",
            "name",
            "note",
            "position",
        ],
    )

    assert attr._is_clean


def _test_attribute_update_inheritable(attr: BaseAttribute):
    """
    Common routine to check update of isInheritable for label/relation.

    isInheritable uses a different code path since it can't be changed -- the
    attribute needs to be deleted and created again, so need to have separate
    tests for it.
    """
    assert attr._is_clean

    attr.inheritable = True
    assert attr._is_dirty

    attr.inheritable = False
    assert attr._is_clean

    attr.inheritable = True
    assert attr._is_dirty

    attr.flush()
    assert attr._is_clean

    attr.invalidate()
    assert attr.inheritable is True
