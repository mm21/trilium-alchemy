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
