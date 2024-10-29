from typing import Generator
import os
import datetime
import logging
import sys

from pytest import Config, Parser, fixture, raises

from trilium_alchemy import (
    Session,
    Note,
    Attribute,
    Branch,
    Entity,
    ReadOnlyError,
)

from trilium_client import DefaultApi
from trilium_client.models.create_note_def import CreateNoteDef
from trilium_client.models.note import Note as EtapiNoteModel
from trilium_client.models.attribute import Attribute as EtapiAttributeModel
from trilium_client.models.branch import Branch as EtapiBranchModel
from trilium_client.exceptions import NotFoundException

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

load_dotenv()

# need all of these to run all tests
assert "TRILIUM_HOST" in os.environ
assert "TRILIUM_TOKEN" in os.environ
assert "TRILIUM_PASSWORD" in os.environ
assert "TRILIUM_DATA_DIR" in os.environ  # to confirm backup was created

HOST = os.environ["TRILIUM_HOST"]
TOKEN = os.environ["TRILIUM_TOKEN"]
PASSWORD = os.environ["TRILIUM_PASSWORD"]
DATA_DIR = os.environ["TRILIUM_DATA_DIR"]

MARKERS = [
    "auto_flush",
    "default_session",
    "attribute",
    "label",
    "relation",
    "note_title",
    "note_type",
    "note_mime",
    "skip_teardown",
    "setup",
    "temp_file",
]


def pytest_configure(config: Config) -> None:
    for marker in MARKERS:
        config.addinivalue_line("markers", marker)


def pytest_addoption(parser: Parser):
    parser.addoption(
        "--clobber",
        action="store_true",
        help="Allow tests to delete any existing notes. Do not use on production Trilium instance; your notes will be deleted.",
    )
    parser.addoption(
        "--skip-teardown",
        action="store_true",
        help="Skip teardown of test notes for manual inspection",
    )


def pytest_collection_modifyitems(config, items):
    """
    Hook to tune the order of executed tests for specific cases:

    - Move singleton tests to beginning
        - This clobbers any existing notes, so do this first in case we want
        to pass --skip-teardown for inspection
    """

    SINGLETON_TESTS = "test/declarative/test_singleton.py"

    tests = [item.nodeid for item in items]

    singleton_tests = [
        test for test in tests if test.startswith(SINGLETON_TESTS)
    ]

    # insert at beginning in reverse order to preserve order
    for test in reversed(singleton_tests):
        index = [item.nodeid for item in items].index(test)
        items.insert(0, items.pop(index))


@fixture(autouse=True)
def newline(request):
    """
    Print a newline and underline test name.
    """
    print("\n" + "-" * len(request.node.nodeid))


@fixture(autouse=True, scope="session")
def session_setup(request):
    """
    Ensure there are no non-system notes under root; these may be clobbered by
    a test case.
    """
    if not request.config.getoption("--clobber"):
        session = create_session()
        root = get_note(session.api, "root")

        assert root is not None

        for branch_id in root.child_branch_ids:
            branch = get_branch(session.api, branch_id)

            if not branch.note_id.startswith("_"):
                # non-hidden child found: fail test session
                sys.exit(
                    "Root children found and may be deleted by a test case; pass --clobber to ignore. Do not run test cases on production Trilium instance."
                )

    yield


@fixture
def session(request) -> Generator[Session, None, None]:
    """
    Create a new Session.

    Most testing is done using non-default Session, which is the case more
    likely to go wrong e.g. if passing a Session is missed in implementation.

    Also allows each test to create its own session by default, but a default
    session can be specified by using `@mark.default_session`.
    """

    if request.node.get_closest_marker("default_session"):
        default = True
    else:
        default = False

    session = create_session(default=default)

    yield session

    session.deregister_default()


def create_session(default=False):
    return Session(HOST, token=TOKEN, default=default)


@fixture
def note(request, session: Session) -> Generator[Note, None, None]:
    """
    Create a new note "manually" using ETAPI directly; don't rely on framework
    under test to do so.

    Supports attribute creation using decorator like:

    @mark.attribute('test_label', 'test_value')
    @mark.attribute('test_label', inheritable=True)
    @mark.attribute('test_relation', 'target_note_id', type='relation')

    Use @mark.attribute to preserve order of attributes.

    Use @mark.label, @mark.relation only when using label/relation fixtures.
    """
    note = create_note_fixture(request, session, "note")
    yield note
    teardown_note(request, session, note.note_id)


@fixture
def note1(request, session: Session) -> Generator[Note, None, None]:
    note = create_note_fixture(request, session, "note1")
    yield note
    teardown_note(request, session, note.note_id)


@fixture
def note2(request, session: Session, note1) -> Generator[Note, None, None]:
    """
    Take dummy note1 to ensure:
    - note1 is created before note2
    - note2 is cleaned up before note1

    This allows use of note1 and note2 as parent and child, respectively.
    """
    note = create_note_fixture(request, session, "note2")
    yield note
    teardown_note(request, session, note.note_id)

    # TODO: lookup note, ensure parent is in parent branches


@fixture
def label(request, session: Session, note: Note):
    """
    Create a new label.
    """
    # get label config
    marker = request.node.get_closest_marker("label")

    name = marker.args[0]

    if len(marker.args) > 1:
        value = marker.args[1]
    else:
        value = ""

    model = create_label(session.api, note, name, value)

    yield Attribute._from_model(model, session=session, owning_note=note)


@fixture
def relation(request, session: Session, note: Note):
    """
    Create a new relation.
    """
    # get relation config
    marker = request.node.get_closest_marker("relation")

    name = marker.args[0]

    # value (target note id) must be provided for relation
    value = marker.args[1]

    model = create_relation(session.api, note, name, value, request.node.name)

    yield Attribute._from_model(model, session=session, owning_note=note)


@fixture
def branch(request, session: Session, note1: Note, note2: Note):
    model = create_branch(
        session.api,
        note_id=note2.note_id,
        parent_note_id=note1.note_id,
        note_position=10,
        prefix="",
        is_expanded=False,
    )

    # re-fetches model from server, but there's no use case for loading
    # branch with prefetched model besides this, so no need to support it yet
    yield Branch._from_id(model.branch_id, session=session)

    # branch will be automatically deleted when note2 is deleted


@fixture
def note_setup(request, session: Session):
    """
    Ensure note is in expected state based on marker.
    """
    for marker in request.node.iter_markers("setup"):
        note_id = marker.args[0]

        exist = marker.kwargs.get("exist", True)
        clean = marker.kwargs.get("clean", False)
        change = marker.kwargs.get("change", False)

        if exist:
            # make sure note exists

            if note_exists(session.api, note_id):
                # check if user requested clean note
                if clean:
                    clean_note(session.api, note_id)
                # check if user requested changed note
                elif change:
                    change_note(session.api, note_id)
            else:
                # TODO: create note
                pass

        else:
            # make sure note doesn't exist

            if note_exists(session.api, note_id):
                # delete note
                delete_note(session.api, note_id)
            else:
                # do nothing
                pass


@fixture
def temp_file(request, tmp_path: str):
    marker = request.node.get_closest_marker("temp_file")
    content = marker.args[0] if marker else ""

    file_path = f"{tmp_path}/temp.txt"

    if isinstance(content, str):
        mode = "w"
    else:
        mode = "wb"

    with open(file_path, mode) as fh:
        fh.write(content)

    print(f"Created temp file: {file_path}")

    return file_path


"""
Helper functions to implement fixtures.
"""


def create_note_fixture(request, session: Session, fixture_name: str):
    """
    Collect attribute markers as (args, kwargs).

    There's a single attributes marker rather than separate label/relation
    markers since in that case we wouldn't know what order the user wants them
    in. They need to use the same marker to preserve the order.
    """
    attributes = [
        (m.args, m.kwargs) for m in request.node.iter_markers("attribute")
    ]

    # get attributes in order provided by user
    attributes.reverse()

    print(f"Creating {fixture_name} with attributes: {attributes}")

    # get title/type/mime from marker
    marker_title = request.node.get_closest_marker("note_title")
    marker_type = request.node.get_closest_marker("note_type")
    marker_mime = request.node.get_closest_marker("note_mime")

    note_type = "text"
    note_mime = "text/html"

    # override title/type/mime if specified

    if (
        marker_title
        and marker_title.kwargs.get("fixture", "note") == fixture_name
    ):
        note_title = marker_title.args[0]
    else:
        # generate title based on timestamp
        now = str(datetime.datetime.now())
        note_title = f"Test note {now}"

    if (
        marker_type
        and marker_type.kwargs.get("fixture", "note") == fixture_name
    ):
        note_type = marker_type.args[0]

    if (
        marker_mime
        and marker_mime.kwargs.get("fixture", "note") == fixture_name
    ):
        note_mime = marker_mime.args[0]

    note_id = create_note(
        session.api,
        parent_note_id="root",
        title=note_title,
        type=note_type,
        mime=note_mime,
        content="",
    )

    print(f"  Created {fixture_name} with note_id={note_id}")

    # mapping of attribute name to number of attributes
    # (just in case there are multiple attributes with same name,
    # each will get a unique id)
    name_dict = dict()
    position = 10

    # create attributes
    for args, kwargs in attributes:
        # skip if this attribute doesn't apply to this note
        if "fixture" in kwargs and kwargs["fixture"] != fixture_name:
            continue

        name = args[0]

        if len(args) > 1:
            value = args[1]
        else:
            value = ""

        if "type" in kwargs:
            attribute_type = kwargs["type"]
            assert attribute_type in {"label", "relation"}
        else:
            # default to label
            attribute_type = "label"

        if "inheritable" in kwargs:
            is_inheritable = kwargs["inheritable"]
        else:
            is_inheritable = False

        # get index of this attribute (nth attribute with this name)
        if name in name_dict:
            index = name_dict[name]
            name_dict[name] += 1
        else:
            index = 0
            name_dict[name] = 1

        # create attribute
        create_attribute(
            session.api,
            note_id=note_id,
            type=attribute_type,
            name=name,
            value=value,
            is_inheritable=is_inheritable,
            position=position,
        )

        position += 10

    return Note._from_id(note_id, session=session)


# Create note, returning note_id
def create_note(api: DefaultApi, **kwargs) -> str:
    create_note_def = CreateNoteDef(**kwargs)
    response = api.create_note(create_note_def)
    note_id = response.note.note_id

    return note_id


def teardown_note(request, session: Session, note_id: str) -> None:
    if not request.node.get_closest_marker(
        "skip_teardown"
    ) and not request.config.getoption("--skip-teardown"):
        delete_note(session.api, note_id)


def delete_note(api: DefaultApi, note_id: str):
    # delete all attributes first
    note = get_note(api, note_id)
    for attr in note.attributes:
        if attr.note_id == note_id:
            delete_attribute(api, attr.attribute_id)

    api.delete_note_by_id(note_id)


def clean_note(api: DefaultApi, note_id: str) -> None:
    note = get_note(api, note_id)

    # reset title/type/mime
    if note_id == "root":
        title = note_id
    else:
        title = ""
    api.patch_note_by_id(
        note_id, EtapiNoteModel(title=title, type="text", mime="text/html")
    )

    # clean attributes
    for attr in note.attributes:
        delete_attribute(api, attr.attribute_id)

    # clean child branches
    for branch_id in note.child_branch_ids:
        branch = get_branch(api, branch_id)

        # don't delete system branches
        if not branch.note_id.startswith("_"):
            delete_branch(api, branch_id)


def change_note(api: DefaultApi, note_id: str) -> None:
    if note_id.startswith("_"):
        return

    note = get_note(api, note_id)

    # change title/type/mime
    model = EtapiNoteModel(
        title=f"{note.title}_new",
        type="book" if note.type == "text" else "text",
        mime="text/plain" if note.mime == "text/html" else "text/html",
    )

    # commit changes
    api.patch_note_by_id(note_id, model)

    # change attributes
    for attribute in note.attributes:
        if attribute.note_id == note_id:
            change_attribute(api, attribute)

    # change child branches
    for branch_id in note.child_branch_ids:
        change_branch(api, branch_id)


def get_note(api: DefaultApi, note_id: str) -> EtapiNoteModel:
    try:
        model = api.get_note_by_id(note_id)
    except NotFoundException as e:
        model = None

    return model


def note_exists(api: DefaultApi, note_id: str):
    return get_note(api, note_id) is not None


def note_cleanup(note: Note):
    """
    Flush and then delete note so we don't get warnings when flushing it
    after deleting due to abandoned dependencies.
    """

    note.session.flush()
    note.delete()
    note.flush()


def change_attribute(api: DefaultApi, attribute: EtapiAttributeModel):
    assert attribute.type in {"label", "relation"}

    model = EtapiAttributeModel(
        value=f"{attribute.value}_new" if attribute.type == "label" else None,
        position=attribute.position + 10,
    )

    # commit changes
    api.patch_attribute_by_id(attribute.attribute_id, model)


def change_branch(api: DefaultApi, branch_id: str):
    branch = get_branch(api, branch_id)

    if branch.note_id.startswith("_"):
        return

    model = EtapiBranchModel(
        prefix=f"{branch.prefix}_new",
        note_position=branch.note_position + 10,
        is_expanded=not branch.is_expanded,
    )

    api.patch_branch_by_id(branch_id, model)

    change_note(api, branch.note_id)


def create_label(
    api: DefaultApi, note: Note, name: str, value: str
) -> EtapiAttributeModel:
    return create_attribute(
        api,
        note_id=note.note_id,
        type="label",
        name=name,
        value=value,
        is_inheritable=False,
        position=10,
    )


def create_relation(
    api: DefaultApi, note: Note, name: str, value: str, prefix: str
) -> EtapiAttributeModel:
    return create_attribute(
        api,
        note_id=note.note_id,
        type="relation",
        name=name,
        value=value,
        is_inheritable=False,
        position=10,
    )


def create_attribute(api: DefaultApi, **kwargs) -> EtapiAttributeModel:
    # create model
    model = EtapiAttributeModel(**kwargs)

    # invoke api
    model_new = api.post_attribute(model)
    assert model_new is not None

    return model_new


def get_attribute(api: DefaultApi, attribute_id: str) -> EtapiAttributeModel:
    try:
        model = api.get_attribute_by_id(attribute_id)
    except NotFoundException as e:
        model = None

    return model


def delete_attribute(api: DefaultApi, attribute_id: str) -> None:
    api.delete_attribute_by_id(attribute_id)


def attribute_exists(api: DefaultApi, attribute_id: str) -> bool:
    return get_attribute(api, attribute_id) is not None


def create_branch(api: DefaultApi, **kwargs) -> EtapiBranchModel:
    # create model
    model = EtapiBranchModel(**kwargs)

    # invoke api
    model_new = api.post_branch(model)
    assert model_new is not None

    # print(f'Created branch: {model_new}')

    return model_new


def delete_branch(api: DefaultApi, branch_id: str) -> None:
    api.delete_branch_by_id(branch_id)


def get_branch(api: DefaultApi, branch_id: str) -> EtapiBranchModel | None:
    try:
        model = api.get_branch_by_id(branch_id)
    except NotFoundException as e:
        model = None

    return model


def branch_exists(api: DefaultApi, branch_id: str) -> bool:
    return get_branch(api, branch_id) is not None


def check_read_only(entity: Entity, fields: list[str]):
    for field in fields:
        with raises(ReadOnlyError):
            # set dummy value of None; exception should be raised
            setattr(entity, field, None)
