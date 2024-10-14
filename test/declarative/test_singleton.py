from pytest import mark, fixture
from trilium_alchemy import *
from trilium_alchemy.core.entity.types import State
from trilium_alchemy.core.note.note import id_hash
from typing import cast

from ..conftest import create_session, note_exists, clean_note, delete_note

"""
TODO:

- test passing in note_id when instantiating root non-singleton note
  (example/event-tracker covers this)
    - sets child ids based on provided id

- leaf = True
    - can't declaratively have child notes, ensure exception raised
    - ensure user-created children are preserved
"""


@fixture(autouse=True, scope="module")
def singleton_setup(request):
    yield

    # cleanup singleton tests
    if not request.config.getoption("--skip-teardown"):
        # clean root if exists
        session = create_session()

        if note_exists(session.api, "testSingletonRoot"):
            delete_note(session.api, "testSingletonRoot")


@label("child1")
class TemplateChild1(Note):
    singleton = True
    title = "Child 1"
    note_type = "book"
    mime = "text/plain"


class IdempotentTest1(Note):
    idempotent = True


class SegmentTestChild(Note):
    note_id_segment = "Child"


@children(SegmentTestChild)
class SegmentTestParent(Note):
    note_id_seed = "Parent"


def check_child1(branch: Branch):
    assert branch.prefix == ""
    assert branch.expanded is False

    note = branch.child

    assert note.singleton
    assert not note.leaf
    assert note.note_id == id_hash(f"{__name__}.TemplateChild1")
    assert note.title == "Child 1"
    assert note.note_type == "book"
    assert note.mime == "text/plain"

    assert len(note.attributes.owned) == 1
    child1 = note.attributes.owned[0]

    assert child1.name == "child1"

    assert len(note.branches.children) == 0
    assert len(note.branches.parents) == 2


# TODO: ensure declaratively adding children fails when leaf = True


@relation("child1", TemplateChild1)
class TemplateChild2(Note):
    singleton = True
    leaf = True


def check_child2(branch: Branch):
    assert branch.prefix == ""
    assert branch.expanded is False

    note = branch.child

    assert note.singleton
    assert note.leaf
    assert note.note_id == id_hash(f"{__name__}.TemplateChild2")
    assert note.title == "TemplateChild2"
    assert note.note_type == "text"
    assert note.mime == "text/html"

    assert len(note.attributes.owned) == 1
    assert note.attributes.owned[0].name == "child1"
    assert note.attributes.owned[0].target.note_id == id_hash(
        f"{__name__}.TemplateChild1"
    )

    assert len(note.branches.children) == 0
    assert len(note.branches.parents) == 2


@label_def("label1")
@relation_def("relation1", multi=True, inverse="relation1inverse")
@children(TemplateChild1, TemplateChild2)
class TemplateTest(Template):
    pass


def check_template_attributes(attributes):
    assert len(attributes) == 3

    label1, relation1, template = attributes

    assert label1.name == "label:label1"
    assert label1.value == "promoted,single,text"

    assert relation1.name == "relation:relation1"
    assert relation1.value == "promoted,multi,inverse=relation1inverse"

    assert template.name == "template"
    assert template.value == ""


def check_template(branch: Branch):
    assert branch.prefix == ""
    assert branch.expanded is False

    note = branch.child

    assert note.note_id == id_hash("TemplateTest")
    assert note.title == "TemplateTest"
    assert note.note_type == "text"
    assert note.mime == "text/html"

    check_template_attributes(note.attributes.owned)

    assert len(note.branches.children) == 2
    check_child1(note.branches.children[0])
    check_child2(note.branches.children[1])


class TemplateChild3(Note):
    singleton = True


class TemplateChild3_2(Note):
    singleton = True


def check_child3(branch: Branch):
    assert branch.prefix == "my_prefix"
    assert branch.expanded is True

    note = branch.child

    name = type(note).__name__

    assert note.singleton
    assert not note.leaf
    assert note.note_id == id_hash(f"{__name__}.{name}")
    assert note.title == name
    assert note.note_type == "text"
    assert note.mime == "text/html"

    assert len(note.attributes.owned) == 0
    assert len(note.branches.children) == 0
    assert len(note.branches.parents) == 1


# test both ways of adding children with branch args
@label("label3")
@children((TemplateChild3, {"prefix": "my_prefix", "expanded": True}))
@child(TemplateChild3_2, prefix="my_prefix", expanded=True)
class TemplateSubclass(TemplateTest):
    pass


def check_subclass(branch: Branch):
    assert branch.prefix == ""
    assert branch.expanded is False

    note = branch.child

    assert note.note_id == id_hash(f"TemplateSubclass")
    assert note.title == "TemplateSubclass"
    assert note.note_type == "text"
    assert note.mime == "text/html"

    assert len(note.attributes.owned) == 4

    label3 = note.attributes.owned[0]
    assert label3.name == "label3"
    assert label3.value == ""

    check_template_attributes(note.attributes.owned[1:])

    assert len(note.branches.children) == 4
    check_child3(note.branches.children[0])
    check_child3(note.branches.children[1])
    check_child1(note.branches.children[2])
    check_child2(note.branches.children[3])


@label("hideChildrenOverview", inheritable=True)
@label("mapType", "link", inheritable=True)
@children(TemplateTest, TemplateSubclass)
class SingletonRoot(Note):
    note_id = "testSingletonRoot"


def check_inherited_attributes(note: Note):
    if note.note_id != "testSingletonRoot":
        # check inherited attributes

        assert len(note.attributes.inherited) == 2
        label1, label2 = note.attributes.inherited

        assert label1.name == "hideChildrenOverview"
        assert label1.value == ""

        assert label2.name == "mapType"
        assert label2.value == "link"

    # recurse into children
    for branch in note.branches.children:
        check_inherited_attributes(branch.child)


def check_root(root: SingletonRoot, state: State):
    # recursively check states
    check_note_state(root, state)

    if state is not state.CREATE:
        # if already created, recursively check inherited attributes
        assert root._model.exists
        check_inherited_attributes(root)
    else:
        assert not root._model.exists

    assert root.note_id == "testSingletonRoot"
    assert root.title == "SingletonRoot"
    assert root.note_type == "text"
    assert root.mime == "text/html"

    assert len(root.attributes.owned) == 3

    hco, map_type, css_class = root.attributes.owned

    assert hco.name == "hideChildrenOverview"
    assert hco.value == ""
    assert map_type.name == "mapType"
    assert map_type.value == "link"
    assert css_class.name == "cssClass"
    assert css_class.value == "triliumAlchemyDeclarative"

    assert len(root.branches.children) == 2
    check_template(root.branches.children[0])
    check_subclass(root.branches.children[1])

    assert root._session._root_position_base == 999999999

    # check positions of children
    for idx in range(len(root.branches.children)):
        branch = root.branches.children[idx]
        assert branch.position == (idx + 1) * 10


def check_note_state(note: Note, state: State):
    """
    Recursively ensure note and its attributes are in provided state.
    """
    assert note._state is state

    # check attributes
    for attr in note.attributes.owned:
        assert attr._state is state

    # check children
    for branch in note.branches.children:
        assert branch._state is state
        check_note_state(branch.child, state)


# TODO: add pre-existing attributes/branches of root, ensure deleted
# - use note fixture, set note id in marker?
@mark.dependency()
@mark.setup("testSingletonRoot", exist=False)
def test_create(session: Session, note_setup):
    """
    Create singleton hierarchy.
    """
    root = SingletonRoot(session=session, parents=session.root)
    check_root(root, State.CREATE)
    session.flush()


@mark.dependency(depends=["test_create"])
def test_clean(session: Session):
    """
    Make sure singleton is clean after being previously created.
    """
    root = SingletonRoot(session=session)
    check_root(root, State.CLEAN)
    assert len(session._cache.dirty_set) == 0


@mark.dependency(depends=["test_clean"])
@mark.setup("testSingletonRoot", change=True)
def test_update(session: Session, note_setup):
    """
    Make sure singleton is updated after being changed.
    """
    root = SingletonRoot(session=session)
    check_root(root, State.UPDATE)
    session.flush()


@mark.dependency(depends=["test_clean"])
def test_instance(request, session: Session):
    """
    Create a new note which has TemplateTest as a template.
    """
    root = Note(note_id="testSingletonRoot", session=session)
    inst = Note(
        title="TemplateTest instance",
        parents=root,
        template=TemplateTest,
        session=session,
    )

    assert inst.note_id is None
    assert inst._is_create

    assert len(inst.attributes.owned) == 1
    template = cast(Relation, inst.attributes.owned[0])

    assert template.name == "template"
    assert template.target.note_id == id_hash(f"TemplateTest")
    assert template.target is TemplateTest(session=session)

    inst.flush()
    template.flush()

    assert inst._is_clean


def test_idempotent(session: Session):
    note = IdempotentTest1(session=session)
    assert note.note_id == id_hash("IdempotentTest1")


def test_note_id_segment(session: Session):
    parent = SegmentTestParent(session=session)
    assert parent.note_id == id_hash("Parent")
    assert len(parent.children) == 1

    child = parent.children[0]
    assert isinstance(child, SegmentTestChild)
    assert child.note_id == id_hash(f"{parent.note_id}_Child_0")
