from pytest import mark, raises

from trilium_alchemy import *

"""
Test basic CRUD capability of note's attributes via indexing into {obj}`Note`
by attribute name.
"""


def test_create(session: Session, note: Note):
    # create attribute
    note["label1"] = ""
    assert note["label1"] == ""
    assert "label1" in note


@mark.attribute("label1", "value1")
def test_update(session: Session, note: Note):
    # update / get attribute
    note["label1"] = "value2"
    note.flush()
    assert note["label1"] == "value2"


@mark.attribute("label1", "value1")
def test_del(session: Session, note: Note):
    # del / not in attribute
    del note["label1"]
    assert len(note) == 0
    assert "label1" not in note

    with raises(KeyError):
        _ = note["label1"]


def test_get(session: Session, note: Note):
    # get attribute
    assert note.get("label1") is None
    assert note.get("label1", "value1") == "value1"


@mark.attribute("label1", "value1")
@mark.attribute("label2", "value2")
@mark.attribute("label3", "value3")
@mark.attribute("label4", "value4")
@mark.attribute("label5", "value5")
def test_iter(session: Session, note: Note):
    # len / iterate over attributes
    assert len(note) == 5

    keys = [
        "label1",
        "label2",
        "label3",
        "label4",
        "label5",
    ]

    values = [
        "value1",
        "value2",
        "value3",
        "value4",
        "value5",
    ]

    assert list(note) == keys
    assert list(note.keys()) == keys
    assert list(note.values()) == values

    assert list(note.items()) == [
        ("label1", "value1"),
        ("label2", "value2"),
        ("label3", "value3"),
        ("label4", "value4"),
        ("label5", "value5"),
    ]


@mark.attribute("label1", "value1")
@mark.attribute("label1", "value2")
def test_multi(session: Session, note: Note):
    # multi-valued label
    assert len(note) == 1
    assert len(note.attributes["label1"]) == 2
    assert note["label1"] == "value1"


@mark.attribute("label1", "value1", inheritable=True, fixture="note1")
@mark.attribute("label1", "value2", fixture="note2")
@mark.attribute(
    "relation1", "root", inheritable=True, fixture="note1", type="relation"
)
@mark.attribute("relation1", "root", fixture="note2", type="relation")
def test_filter_labels(note1: Note, note2: Note, branch: Branch):
    # note1, owned/inherited labels

    note1_labels = note1.labels.filter("label1")

    assert len(note1_labels) == 1
    assert note1_labels[0].value == "value1"
    assert len(note1.labels.filter("label2")) == 0

    assert len(note1.labels.owned) == 1
    assert note1.labels.owned[0].value == "value1"

    assert len(note1.labels.inherited) == 0

    # note2, owned/inherited labels

    note2_labels = note2.labels.filter("label1")

    assert len(note2_labels) == 2
    assert note2_labels[0].value == "value2"
    assert note2_labels[1].value == "value1"

    assert len(note2.labels.owned) == 1
    assert note2.labels.owned[0].value == "value2"

    assert len(note2.labels.inherited) == 1
    assert note2.labels.inherited[0].value == "value1"

    # note1, owned/inherited relations

    note1_relations = note1.relations.filter("relation1")

    assert len(note1_relations) == 1
    assert note1_relations[0].target.note_id == "root"
    assert len(note1.relations.filter("relation2")) == 0

    assert len(note1.relations.owned) == 1
    assert note1.relations.owned[0].target.note_id == "root"

    assert len(note1.relations.inherited) == 0

    # note2, owned/inherited relations

    note2_relations = note2.relations.filter("relation1")

    assert len(note2_relations) == 2
    assert note2_relations[0].target.note_id == "root"
    assert note2_relations[0].inheritable is False

    assert note2_relations[1].target.note_id == "root"
    assert note2_relations[1].inheritable is True

    assert len(note2.relations.owned) == 1
    assert note2.relations.owned[0].target.note_id == "root"
    assert note2.relations.owned[0].inheritable is False

    assert len(note2.relations.inherited) == 1
    assert note2.relations.inherited[0].target.note_id == "root"
    assert note2.relations.inherited[0].inheritable is True
