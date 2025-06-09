import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Generator

import dotenv
from pytest import Config, FixtureRequest, Parser, fixture, raises
from trilium_client import DefaultApi
from trilium_client.exceptions import NotFoundException
from trilium_client.models.attribute import Attribute as EtapiAttributeModel
from trilium_client.models.branch import Branch as EtapiBranchModel
from trilium_client.models.create_note_def import CreateNoteDef
from trilium_client.models.note import Note as EtapiNoteModel

from trilium_alchemy import (
    BaseAttribute,
    BaseEntity,
    Branch,
    Note,
    ReadOnlyError,
    Session,
)

# enable import of modules in test folder
sys.path.insert(0, os.getcwd())

logging.basicConfig(level=logging.WARNING)

dotenv.load_dotenv()

# need all of these to run all tests
assert "TRILIUM_HOST" in os.environ
assert "TRILIUM_TOKEN" in os.environ
assert "TRILIUM_PASSWORD" in os.environ
assert "TRILIUM_DATA_DIR" in os.environ  # to confirm backup was created

HOST = os.environ["TRILIUM_HOST"]
TOKEN = os.environ["TRILIUM_TOKEN"]
PASSWORD = os.environ["TRILIUM_PASSWORD"]

DATA_DIR = Path(os.environ["TRILIUM_DATA_DIR"])
DB_PATH = DATA_DIR / "document.db"
BACKUP_PATH = DATA_DIR / "backup"

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
    "skip_cleanup",
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
        help="Allow tests to delete any existing notes; do not use on production Trilium instance as your notes will be deleted",
    )
    parser.addoption(
        "--skip-teardown",
        action="store_true",
        help="Skip teardown of test notes for manual inspection",
    )
    parser.addoption(
        "--cli-stdout",
        action="store_true",
        help="Print stdout of CLI commands",
    )


@fixture(autouse=True)
def newline(request):
    """
    Print a newline and underline test name.
    """
    print("\n" + "-" * len(request.node.nodeid))


@fixture(autouse=True)
def cleanup_tree(request: FixtureRequest):
    """
    Cleanup existing tree and ensure this testcase cleaned up its notes
    afterward.
    """
    if request.config.getoption(
        "--skip-teardown"
    ) or request.node.get_closest_marker("skip_cleanup"):
        yield
        return

    session = create_session()
    root = get_root_note(session.api)

    # delete root children
    delete_children(session.api, root)

    # delete root attributes
    for attribute in root.attributes:
        assert attribute.attribute_id
        delete_attribute(session.api, attribute.attribute_id)

    # run test
    yield

    # ensure test cleaned up
    root = get_root_note(session.api)
    assert root.attributes is not None

    assert (
        len(get_branches(session.api, root)) == 0
    ), "Test did not cleanup root notes"
    assert len(root.attributes) == 0, "Test did not cleanup root attributes"


@fixture(autouse=True, scope="session")
def session_setup(request: FixtureRequest):
    """
    Ensure there are no non-system notes under root; these may be clobbered by
    a testcase.
    """
    if not request.config.getoption("--clobber"):
        session = create_session()
        root = get_root_note(session.api)
        assert root.child_branch_ids is not None

        if len(get_branches(session.api, root)):
            # non-hidden child found: fail test session
            sys.exit(
                "Root note children found and may be deleted by a testcase; pass --clobber to ignore. Do not run test cases on production Trilium instance."
            )

        if root.attributes:
            sys.exit(
                "Root note attributes found and will be deleted by a testcase; pass --clobber to ignore. Do not run test cases on production Trilium instance."
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
def note(
    request: FixtureRequest, session: Session
) -> Generator[Note, None, None]:
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
def note1(
    request: FixtureRequest, session: Session
) -> Generator[Note, None, None]:
    note = create_note_fixture(request, session, "note1")
    yield note
    teardown_note(request, session, note.note_id)


@fixture
def note2(
    request: FixtureRequest, session: Session, note1
) -> Generator[Note, None, None]:
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
def label(request: FixtureRequest, session: Session, note: Note):
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

    yield BaseAttribute._from_model(model, session=session, owning_note=note)


@fixture
def relation(request: FixtureRequest, session: Session, note: Note):
    """
    Create a new relation.
    """
    # get relation config
    marker = request.node.get_closest_marker("relation")

    name = marker.args[0]

    # value (target note id) must be provided for relation
    value = marker.args[1]

    model = create_relation(session.api, note, name, value)

    yield BaseAttribute._from_model(model, session=session, owning_note=note)


@fixture
def branch(request: FixtureRequest, session: Session, note1: Note, note2: Note):
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
def note_setup(request: FixtureRequest, session: Session):
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
def temp_file(request: FixtureRequest, tmp_path: Path):
    marker = request.node.get_closest_marker("temp_file")
    content = marker.args[0] if marker else ""

    file_path = tmp_path / "temp.txt"

    if isinstance(content, str):
        mode = "w"
    else:
        mode = "wb"

    with file_path.open(mode) as fh:
        fh.write(content)

    print(f"Created temp file: {file_path}")

    return file_path


@fixture
def skip_teardown(request: FixtureRequest) -> bool:
    """
    Skip teardown if flag was passed.
    """
    return bool(request.config.getoption("--skip-teardown"))


"""
Helper functions to implement fixtures.
"""


def create_note_fixture(
    request: FixtureRequest, session: Session, fixture_name: str
):
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
            name_dict[name] += 1
        else:
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


def teardown_note(
    request: FixtureRequest, session: Session, note_id: str
) -> None:
    if not request.node.get_closest_marker(
        "skip_teardown"
    ) and not request.config.getoption("--skip-teardown"):
        delete_note(session.api, note_id)


def delete_note(api: DefaultApi, note_id: str):
    api.delete_note_by_id(note_id)


def delete_children(api: DefaultApi, note: EtapiNoteModel):
    for branch in get_branches(api, note):
        delete_branch(api, branch)


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
    delete_children(api, note)

    # clean content
    api.put_note_content_by_id(note_id, "")


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


def get_note(api: DefaultApi, note_id: str) -> EtapiNoteModel | None:
    try:
        model = api.get_note_by_id(note_id)
    except NotFoundException:
        model = None

    return model


def get_root_note(api: DefaultApi) -> EtapiNoteModel:
    root = get_note(api, "root")
    assert root is not None
    return root


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
    api: DefaultApi, note: Note, name: str, value: str, position: int = 10
) -> EtapiAttributeModel:
    return create_attribute(
        api,
        note_id=note.note_id,
        type="label",
        name=name,
        value=value,
        is_inheritable=False,
        position=position,
    )


def create_relation(
    api: DefaultApi, note: Note, name: str, value: str, position: int = 10
) -> EtapiAttributeModel:
    return create_attribute(
        api,
        note_id=note.note_id,
        type="relation",
        name=name,
        value=value,
        is_inheritable=False,
        position=position,
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
    except NotFoundException:
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

    return model_new


def delete_branch(api: DefaultApi, branch: EtapiBranchModel) -> None:
    api.delete_branch_by_id(branch.branch_id)


def get_branch(api: DefaultApi, branch_id: str) -> EtapiBranchModel | None:
    try:
        model = api.get_branch_by_id(branch_id)
    except NotFoundException:
        model = None

    return model


def get_branches(
    api: DefaultApi, note: EtapiNoteModel
) -> list[EtapiBranchModel]:
    """
    Get branch models which are not hidden.
    """
    branches: list[EtapiBranchModel] = []

    assert note.child_branch_ids is not None
    for branch_id in note.child_branch_ids:
        branch = get_branch(api, branch_id)
        assert branch
        assert branch.note_id

        if not branch.note_id.startswith("_"):
            branches.append(branch)

    return branches


def branch_exists(api: DefaultApi, branch_id: str) -> bool:
    return get_branch(api, branch_id) is not None


def check_read_only(entity: BaseEntity, fields: list[str]):
    for field in fields:
        with raises((ReadOnlyError, AttributeError)):
            # set dummy value of None; exception should be raised
            setattr(entity, field, None)


def compare_folders(dir1: Path, dir2: Path):
    """
    Ensure the given folders have the same files and the contents match.
    """

    def collect_files(path: Path) -> Generator[Path, None, None]:
        for dirpath, _, filenames in path.walk():
            for filename in filenames:
                yield (dirpath / filename).relative_to(path)

    dir1_files = list(collect_files(dir1))
    dir2_files = list(collect_files(dir2))

    assert set(dir1_files) == set(
        dir2_files
    ), f"Directories do not contain the same files: dir1='{dir1}', dir2='{dir2}'"

    files = sorted(dir1_files)

    for file in files:
        file1, file2 = dir1 / file, dir2 / file
        file1_bytes, file2_bytes = file1.read_bytes(), file2.read_bytes()

        # try comparing as text for better debugging output
        try:
            file1_text, file2_text = file1_bytes.decode(), file2_bytes.decode()
        except UnicodeDecodeError:
            assert file1_bytes == file2_bytes
        else:
            assert file1_text == file2_text
