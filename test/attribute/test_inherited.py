from pytest import mark

from trilium_alchemy import *

"""
Test inheritance via child branch.

Using branch fixture ensures that note2 is a child of note1.
"""


@mark.attribute("label1", inheritable=True, fixture="note1")
def test_child(session: Session, note1: Note, note2: Note, branch: Branch):
    assert len(note2.branches.parents) == 2
    assert note1 in {branch.parent for branch in note2.branches.parents}

    assert len(note2.attributes.owned) == 0

    assert len(note2.attributes.inherited) == 1
    label1 = note2.attributes.inherited[0]
    assert label1.name == "label1"
    assert label1.note is note1
