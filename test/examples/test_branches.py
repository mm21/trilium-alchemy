from pytest import mark

from trilium_alchemy import *


@mark.default_session
def test_iteration(session: Session, note1: Note):
    note = Note(parents=note1)

    # add root as parent of note
    note ^= session.root

    # create child note
    note += Note()

    # iterate over branches
    for branch in note.branches:
        print(branch)

    session.flush()

    note.delete()
    session.flush()


@mark.default_session
def test_add(session: Session, note: Note):
    # for this one we need a note which doesn't already have root as a parent
    note += Note()
    note = note.children[0]

    # add a child note with prefix
    note += Branch(child=Note(title="Child note"), prefix="Child branch prefix")

    # add a parent note (cloning the note) with prefix
    note += Branch(parent=session.root, prefix="Parent branch prefix")

    session.flush()

    # cleanup child note since now it's cloned to root
    note.delete()
    session.flush()
