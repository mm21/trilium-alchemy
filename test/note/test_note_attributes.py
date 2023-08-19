import pytest

from trilium_alchemy import *

"""
Test basic CRUD capability of note's attributes.
"""


def test_set(session: Session, note: Note):
    # set / in attribute
    note["Label1"] = "Value"
    note.flush()
    assert "Label1" in note
    assert note.attributes["Label1"][0].value == "Value"


def test_update(session: Session, note: Note):
    # update / get attribute
    note["Label2"] = "Value"
    note.flush()
    assert note.attributes["Label2"][0].value == "Value"

    note["Label2"] = "New Value"
    note.flush()
    assert note["Label2"] == "New Value"


def test_del(session: Session, note: Note):
    # del / not in attribute
    note["Label3"] = "Value"
    note.flush()
    assert note.attributes["Label3"][0].value == "Value"

    del note["Label3"]
    assert len(note) == 0
    assert "Label3" not in note

    with pytest.raises(KeyError):
        _ = note["Label3"]


def test_get(session: Session, note: Note):
    # get attribute
    assert note.get("Label4") is None
    assert note.get("Label4", "Value") == "Value"


def test_iter(session: Session, note: Note):
    # iterate over attributes
    note["Label5"] = "Value5"
    note["Label6"] = "Value6"
    note["Label7"] = "Value7"
    note["Label8"] = "Value8"
    note["Label9"] = "Value9"
    note.flush()

    assert len(note) == 5

    keys = [
        "Label5",
        "Label6",
        "Label7",
        "Label8",
        "Label9",
    ]

    values = [
        "Value5",
        "Value6",
        "Value7",
        "Value8",
        "Value9",
    ]

    assert list(note) == keys
    assert list(note.keys()) == keys
    assert list(note.values()) == values

    assert list(note.items()) == [
        ("Label5", "Value5"),
        ("Label6", "Value6"),
        ("Label7", "Value7"),
        ("Label8", "Value8"),
        ("Label9", "Value9"),
    ]


# TODO: test multiple value Label