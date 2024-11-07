from pytest import mark

from trilium_alchemy import *


@mark.attribute("label1")
def test_index_get(session: Session, note: Note):
    """
    Test setting an attribute by indexing into .attributes.
    """

    assert note["label1"] == ""

    assert "label1" in note
    assert "label1" in note.attributes
    assert "label1" in note.attributes.owned
    assert "label1" not in note.attributes.inherited

    assert len(note.attributes["label1"]) == 1
    assert len(note.attributes.owned["label1"]) == 1

    assert note.attributes["label1"][0].value == ""
    assert note.attributes.owned["label1"][0].value == ""

    assert note.attributes["label1"][0] is note.attributes.owned["label1"][0]

    label1 = note.attributes.owned["label1"][0]

    assert label1.attribute_type == "label"
    assert label1.name == "label1"
    assert label1.value == ""

    # get numeric indices
    assert label1 is note.attributes[0]
    assert label1 is note.attributes.owned[0]

    session.flush()


def test_labels(session: Session, note: Note):
    assert "label1" not in note.attributes
    assert "label1" not in note.labels
    assert "label1" not in note.labels.owned
    assert "label1" not in note.labels.inherited

    # create list of attributes
    note.attributes = [Label("label1", "value1", session=session)]

    assert "label1" in note.attributes
    assert "label1" in note.labels
    assert "label1" in note.labels.owned
    assert "label1" not in note.labels.inherited

    assert len(note.attributes.get_all("label1")) == 1
    assert len(note.labels.get_all("label1")) == 1
    assert len(note.relations.get_all("label1")) == 0
    assert note["label1"] == "value1"

    label1 = note.labels.get("label1")
    assert label1 is not None
    assert label1.name == "label1"
    assert label1.value == "value1"

    assert label1 is note.attributes[0]
    assert label1 is note.attributes.owned[0]
    assert label1 is note.labels[0]
    assert label1 is note.labels.owned[0]
    assert len(note.labels.inherited) == 0

    # change value of existing attribute
    label1.value = "value2"

    assert note.labels.get_value("label1") == "value2"

    note.labels.set_value("label1", "value3")
    assert label1.value == "value3"

    session.flush()

    # replace with different attribute
    note.attributes.owned[0] = Label("label2", "value1", session=session)

    assert note.attributes.owned[0].name == "label2"
    assert note.labels.get("label2").value == "value1"
    assert note.labels.get_value("label2") == "value1"

    session.flush()

    note.labels.set_value("label2", "value2")
    assert note.labels.get_value("label2") == "value2"

    label2 = note.labels.get("label2")
    assert label2 is not None

    note.labels.set_values("label2", ["value3", "value4"])

    assert label2 is note.labels.get("label2")
    assert len(note.labels.get_all("label2")) == 2
    assert note.labels.get_values("label2") == ["value3", "value4"]

    note.labels.append_value("label2", "value5")

    assert note.labels.get_values("label2") == ["value3", "value4", "value5"]


def test_relations(session: Session, note: Note):
    assert "relation1" not in note.attributes
    assert "relation1" not in note.relations
    assert "relation1" not in note.relations.owned
    assert "relation1" not in note.relations.inherited

    # create list of attributes
    note.attributes = [Relation("relation1", session.root, session=session)]

    assert "relation1" in note.attributes
    assert "relation1" in note.relations
    assert "relation1" in note.relations.owned
    assert "relation1" not in note.relations.inherited

    assert len(note.attributes.get_all("relation1")) == 1
    assert len(note.relations.get_all("relation1")) == 1
    assert len(note.relations.inherited.get_all("relation1")) == 0

    relation1 = note.relations.get("relation1")
    assert relation1 is not None
    assert relation1.name == "relation1"
    assert relation1.target is session.root

    assert relation1 is note.attributes[0]
    assert relation1 is note.attributes.owned[0]
    assert relation1 is note.relations[0]
    assert relation1 is note.relations.owned[0]
    assert len(note.relations.inherited) == 0

    # change value of existing attribute
    relation1.target = note

    assert note.relations.get_value("relation1") is note

    note.relations.set_value("relation1", session.root)
    assert relation1.target is session.root

    session.flush()

    # replace with different attribute
    note.attributes.owned[0] = Relation(
        "relation2", session.root, session=session
    )

    assert note.attributes.owned[0].name == "relation2"
    assert note.relations.get("relation2").target is session.root
    assert note.relations.get_value("relation2") is session.root

    session.flush()

    note.relations.set_value("relation2", note)
    assert note.relations.get_value("relation2") is note

    relation2 = note.relations.get("relation2")
    assert relation2 is not None

    note.relations.set_values("relation2", [session.root, note])

    assert relation2 is note.relations.get("relation2")
    assert len(note.relations.get_all("relation2")) == 2
    assert note.relations.get_values("relation2") == [session.root, note]

    note.relations.append_value("relation2", session.root)

    assert note.relations.get_values("relation2") == [
        session.root,
        note,
        session.root,
    ]


@mark.attribute("label1")
def test_index_del(session: Session, note: Note):
    assert note["label1"] == ""

    # delete by name
    note.attributes["label1"][0].delete()

    assert "label1" not in note.attributes

    # delete by index
    note["label2"] = ""
    del note.attributes[0]

    session.flush()


@mark.attribute("label1", inheritable=True, fixture="note1")
@mark.attribute("label1", "value2", fixture="note2")
def test_index_inherited(
    session: Session, note1: Note, note2: Note, branch: Branch
):
    assert len(note1.attributes) == 1
    assert len(note1.attributes["label1"]) == 1
    assert len(note1.attributes.owned["label1"]) == 1

    assert len(note2.attributes) == 2
    assert len(note2.attributes["label1"]) == 2
    assert len(note2.attributes.owned["label1"]) == 1
    assert len(note2.attributes.inherited["label1"]) == 1

    # test attribute iteration
    count = 0
    for attr in note1.attributes:
        count += 1

    assert count == 1

    # test iteration by numeric index
    assert len(note1.attributes) == 1
    for i in range(len(note1.attributes)):
        attr = note1.attributes[i]
        assert isinstance(attr, BaseAttribute)

    assert len(note1.attributes.owned) == 1
    for i in range(len(note1.attributes.owned)):
        attr = note1.attributes[i]
        assert isinstance(attr, BaseAttribute)

    assert len(note2.attributes.inherited) == 1
    for i in range(len(note1.attributes.inherited)):
        attr = note1.attributes[i]
        assert isinstance(attr, BaseAttribute)

    # no-op, no changes made
    assert len(session.dirty_set) == 0


# Set attribute kwargs using index mechanism
def test_index_kwargs(session: Session, note: Note):
    note.attributes["label1"] = ("value1", {"inheritable": True})

    label1 = note.attributes[0]

    assert label1._is_create
    assert label1.name == "label1"
    assert label1.value == "value1"
    assert label1.inheritable is True

    session.flush()


# Update attribute and use kwargs
@mark.attribute("label1")
@mark.attribute("relation1", "root", type="relation")
def test_index_update(session: Session, note: Note):
    assert len(note.attributes["label1"]) == 1
    assert len(note.attributes["relation1"]) == 1

    assert note["label1"] == ""
    assert note["relation1"].note_id == "root"

    # label update
    note["label1"] = "value1"
    assert note["label1"] == "value1"
    assert note.attributes["label1"][0].inheritable is False

    # label update w/kwargs
    note["label1"] = ("value1-2", {"inheritable": True})
    assert note["label1"] == "value1-2"
    assert note.attributes["label1"][0].inheritable is True

    # relation update
    note["relation1"] = note
    assert note["relation1"] is note
    assert note.attributes["relation1"][0].inheritable is False

    # set target back to root
    note["relation1"] = Note(note_id="root", session=session)
    assert note["relation1"].note_id == "root"

    # relation update w/kwargs
    note["relation1"] = (note, {"inheritable": True})
    assert note["relation1"] is note
    assert note.attributes["relation1"][0].inheritable is True

    session.flush()


def test_append(session: Session, note: Note):
    note += Label("label1", "value1", inheritable=True, session=session)
    assert len(note.attributes) == 1

    label1 = note.attributes[0]
    assert label1.name == "label1"
    assert label1.value == "value1"
    assert label1.inheritable is True

    assert len(note.attributes.owned["label1"]) == 1
    assert note.attributes["label1"][0] is label1
    assert note.attributes.owned["label1"][0] is label1

    assert "label1" not in note.attributes.inherited

    note.attributes.append(Label("label2", session=session))

    assert note.attributes[1].name == "label2"
    assert note.attributes[1].value == ""

    session.flush()


def test_extend(session: Session, note: Note):
    note.attributes += [
        Label("label1", "value1", session=session),
        Label("label2", "value2", inheritable=True, session=session),
    ]
    assert len(note.attributes) == 2
    assert len(note.attributes.owned) == 2

    note.attributes.owned += [
        Label("label3", "value3", session=session),
        Label("label4", "value4", inheritable=True, session=session),
    ]

    assert len(note.attributes) == 4
    assert len(note.attributes.owned) == 4

    for i in range(len(note.attributes)):
        attr = note.attributes[i]
        assert attr is note.attributes.owned[i]

        assert attr.name == f"label{i+1}"
        assert attr.value == f"value{i+1}"

        if (i % 2) == 0:
            assert attr.inheritable is False
        else:
            assert attr.inheritable is True

    session.flush()


def test_slice(session: Session, note: Note):
    # create attributes
    note.attributes[0:3] = [
        Label("label1", session=session),
        Label("label2", session=session),
        Label("label3", session=session),
    ]

    label1, label2, label3 = note.attributes

    assert label1.name == "label1"
    assert label2.name == "label2"
    assert label3.name == "label3"

    assert label1.position == 10
    assert label2.position == 20
    assert label3.position == 30

    session.flush()

    # shift attributes
    note.attributes[0:3] = [Label("label0", session=session)] + note.attributes[
        0:2
    ]

    label0, label1, label2 = note.attributes

    assert label0.name == "label0"
    assert label1.name == "label1"
    assert label2.name == "label2"

    assert label0.position == 10
    assert label1.position == 20
    assert label2.position == 30

    assert label3._is_delete

    session.flush()

    # delete attributes
    del note.attributes[0:2]

    assert label0._is_delete
    assert label1._is_delete
    assert not label2._is_delete

    session.flush()


# TODO: test to verify attempting to add same attr multiple times fails


@mark.label("label1", "value1")
def test_from_id(session: Session, label: Label):
    label.invalidate()
    label_new = BaseAttribute._from_id(label.attribute_id, session=session)

    assert label is label_new
