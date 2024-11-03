from pytest import mark

from trilium_alchemy import *

from ..conftest import note_cleanup


class ChildNote(BaseDeclarativeNote):
    decl_title = "Child note"


@label("sorted")
@children(ChildNote)
class MyNote(BaseDeclarativeNote):
    decl_title = "My note"
    decl_content = "<p>Hello, world!</p>"


@mark.default_session
def test_imperative(session: Session):
    # create new note under root
    note = Note(
        title="My note", content="<p>Hello, world!</p>", parents=session.root
    )

    # add label #sorted
    note += Label("sorted")

    # add child note with branch created implicitly
    note += Note(title="Child 1")

    # add child note with branch created explicitly
    note += Branch(child=Note(title="Child 2"))

    # clone first child to root with branch created implicitly
    note.children[0] ^= session.root

    # add label #hideChildrenOverview
    note["hideChildrenOverview"] = ""
    assert note["hideChildrenOverview"] == ""

    assert "hideChildrenOverview" in note

    note_cleanup(note.children[0])
    note_cleanup(note)


@mark.default_session
def test_declarative(session: Session):
    # create new note under root
    note = MyNote(parents=session.root)
    assert note.title == "My note"

    note_cleanup(note)


@mark.default_session
def test_notes(session: Session):
    note = Note()

    note += [Label("myLabel", "value1"), Label("myLabel", "value2")]

    for attr in note.attributes.owned["myLabel"]:
        print(attr)
