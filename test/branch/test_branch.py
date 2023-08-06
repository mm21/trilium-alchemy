from trilium_alchemy import *
from ..conftest import check_read_only, branch_exists
from pytest import raises

"""
Test basic CRUD capability of branches.
"""


def test_update(session: Session, branch: Branch):
    assert branch._is_clean

    branch.prefix = "prefix1"
    assert branch._is_update

    branch.prefix = ""
    assert branch._is_clean

    branch.expanded = True
    assert branch._is_update

    branch.expanded = False
    assert branch._is_clean

    branch._position = 20
    assert branch._is_update

    branch._position = 10
    assert branch._is_clean

    # ensure can't write read-only fields
    check_read_only(
        branch,
        [
            "branch_id",
            "utc_date_modified",
            "position",
        ],
    )

    branch.prefix = "prefix1"
    branch.expanded = True
    branch._position = 20

    branch.flush()
    assert branch._is_clean

    branch.invalidate()

    assert branch.prefix == "prefix1"
    assert branch.expanded is True
    assert branch.position == 20

    # ensure can't update parent/child
    with raises(AssertionError):
        branch.parent = None

    with raises(AssertionError):
        branch.child = None


def test_delete(session: Session, branch: Branch):
    assert branch._is_clean

    branch.delete()
    assert branch._is_delete

    branch.flush()
    assert branch._is_clean

    assert branch_exists(session.api, branch.branch_id) is False


# Create branch and add to note.branches.parents
def test_parents_add(session: Session, note1: Note, note2: Note):
    branch = Branch(note1, note2, prefix="prefix1", session=session)

    note2.branches.parents.add(branch)

    assert branch in note2.branches.parents
    assert branch in note1.branches.children

    # should have been added to note1's branches.children,
    # setting its position
    assert branch.position == 10
    assert branch._is_create
    assert branch.prefix == "prefix1"

    branch.flush()
    assert branch._is_clean


# Create branch and set note.branches.parents
def test_parents_set(session: Session, note1: Note, note2: Note):
    branch = Branch(note1, note2, prefix="prefix1", session=session)

    note2.branches.parents = {branch}

    assert branch in note2.branches.parents
    assert branch in note1.branches.children

    assert branch.position == 10
    assert branch._is_create
    assert branch.prefix == "prefix1"

    branch.flush()
    assert branch._is_clean


# Create branch and add to note.branches.children
def test_child_create(session: Session, note1: Note, note2: Note):
    branch = Branch(note1, note2, prefix="prefix1", session=session)
    note1.branches.children.append(branch)

    assert branch in note1.branches.children
    assert branch in note2.branches.parents

    assert branch.position == 10
    assert branch._is_create
    assert branch.prefix == "prefix1"

    branch.flush()
    assert branch._is_clean
