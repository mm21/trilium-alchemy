from trilium_alchemy import *


def test_parent_add(session: Session, note1: Note, note2: Note):
    note2.parents += note1

    parent_branch = note1.branches.children[0]

    assert parent_branch.parent is note1
    assert parent_branch.child is note2

    assert note1 in note2.parents
    assert note2 in note1.children

    note1_parent_branch = note1.branches.parents[0]

    print(note1_parent_branch)
    assert note1_parent_branch.parent.note_id == "root"
    assert note1.parents[0].note_id == "root"

    assert len(note1.branches.children) == 1
    assert len(note2.branches.parents) == 2
    branch = note1.branches.children[0]

    assert branch._is_create

    session.flush()

    assert branch._is_clean


def test_parent_add_alt(session: Session, note1: Note, note2: Note):
    note2 ^= note1

    assert note1 in note2.parents
    assert note2 in note1.children

    assert len(note1.branches.children) == 1
    assert len(note2.branches.parents) == 2

    root = Note(note_id="root", session=session)

    note3 = Note(parents={root}, session=session)
    note4 = Note(parents={root}, session=session)

    note2 ^= (note3, "My prefix")
    branch = note2.branches.lookup(note3)
    assert branch.prefix == "My prefix"

    note2 += Branch(parent=note4, session=session)

    assert note3 in note2.parents
    assert note4 in note2.parents
    assert note2 in note3.children
    assert note2 in note4.children

    session.flush()

    note3.delete()
    note4.delete()

    session.flush()


def test_parent_extend(session: Session, note: Note, note1: Note, note2: Note):
    note.parents += [note1]
    note.parents += {note2}

    assert len(note.parents) == 3
    assert len(note.branches.parents) == 3

    for parent in note.parents:
        assert isinstance(parent, Note)

    for branch in note.branches.parents:
        assert isinstance(branch, Branch)

    assert note1 in note.parents
    assert note2 in note.parents

    session.flush()


def test_child_add(session: Session, note: Note, note1: Note, note2: Note):
    note += note1
    note.children += note2

    assert len(note.children) == 2
    assert len(note.branches.children) == 2

    assert note.branches.children[0].prefix == ""
    assert note.branches.children[1].prefix == ""

    assert note in note1.parents
    assert note in note2.parents

    assert note1 in note.children
    assert note2 in note.children

    assert len(note1.branches.parents) == 2
    assert len(note2.branches.parents) == 2

    assert note.branches.children[0]._is_create
    assert note.branches.children[1]._is_create

    session.flush()

    assert note.branches.children[0]._is_clean
    assert note.branches.children[1]._is_clean


def test_child_add_prefix(
    session: Session, note: Note, note1: Note, note2: Note
):
    note += (note1, "My prefix 1")
    note.children += (note2, "My prefix 2")

    assert len(note.children) == 2
    assert len(note.branches.children) == 2

    assert note.branches.children[0].prefix == "My prefix 1"
    assert note.branches.children[1].prefix == "My prefix 2"

    assert note in note1.parents
    assert note in note2.parents

    assert note1 in note.children
    assert note2 in note.children

    assert len(note1.branches.parents) == 2
    assert len(note2.branches.parents) == 2

    assert note.branches.children[0]._is_create
    assert note.branches.children[1]._is_create

    session.flush()

    assert note.branches.children[0]._is_clean
    assert note.branches.children[1]._is_clean


# Add child as branch
def test_child_add_branch(session: Session, note1: Note, note2: Note):
    branch = Branch(
        child=note2, prefix="my_prefix", expanded=True, session=session
    )

    assert branch.parent is None
    assert branch.child is note2

    note1 += branch

    assert branch.parent is note1
    assert note2 in note1.children
    assert note1 in note2.parents

    assert len(note1.branches.children) == 1
    assert len(note2.branches.parents) == 2
    assert branch is note1.branches.children[0]

    assert branch._is_create
    assert branch.prefix == "my_prefix"
    assert branch.expanded is True

    session.flush()

    assert branch._is_clean


def test_child_extend(session: Session, note: Note):
    note2 = Note(title="note2", session=session)
    note3 = Note(title="note3", session=session)
    note4 = Note(title="note4", session=session)

    note += [note2, note3]
    assert len(note.children) == 2

    note.children += [note4]
    assert len(note.children) == 3

    # iteration
    count = 0
    for child in note.children:
        assert isinstance(child, Note)
        assert child.title == f"note{count+2}"
        count += 1

    assert count == 3

    # iteration by index
    for i in range(len(note.children)):
        child = note.children[i]
        assert child.title == f"note{i+2}"

    session.flush()


# TODO: test_parent_extend
