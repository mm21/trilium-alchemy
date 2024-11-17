from pytest import mark

from trilium_alchemy import *


@mark.default_session
def test_iteration(session: Session, note: Note):
    # add some attributes
    note += [
        Label("myLabel"),
        Relation("myRelation", session.root),
    ]

    for attr in note.attributes:
        print(f"Attribute: {attr}")

    note.session.flush()


@mark.default_session
def test_index(note: Note):
    # add a label
    note += Label("myLabel", "myValue")

    print(note.attributes[0])

    assert "myLabel" in note
    assert note["myLabel"] == "myValue"

    note.session.flush()


@mark.default_session
def test_delete(note: Note):
    # add a label
    label = Label("myLabel")
    note += label

    # delete from list
    del note.attributes.owned[0]

    print(f"label.state: {label.state}")

    note.session.flush()


@mark.default_session
def test_assign(note: Note):
    # add a label
    label1 = Label("myLabel1")
    note += label1

    note.flush()

    # assign a new list of attributes
    label2 = Label("myLabel2")
    note.attributes.owned = [label2]

    print(f"label1.state: {label1.state}")
    print(f"label2.state: {label2.state}")

    assert label1.state is State.DELETE
    assert label2.state is State.CREATE

    note.session.flush()
