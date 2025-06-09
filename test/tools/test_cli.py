import datetime
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from pytest import FixtureRequest, skip
from typer.testing import CliRunner

from trilium_alchemy import *
from trilium_alchemy.tools.cli.main import app
from trilium_alchemy.tools.config import Config, InstanceConfig
from trilium_alchemy.tools.fs.tree import _map_note_dir

from ..conftest import (
    BACKUP_PATH,
    DB_PATH,
    HOST,
    TOKEN,
    compare_folders,
    create_label,
)
from .fs_utils import NOTE_1_ID, TREE_DUMP_PATH, create_note_1

DIVIDER = "=" * 40


class LogHandler(logging.Handler):
    """
    Handler to create a list of logs for testcases to access for verification.
    """

    test_logs: list[str]

    def __init__(self):
        super().__init__()
        self.test_logs = []

    def emit(self, record: logging.LogRecord):
        self.test_logs.append(record.message)


# create and register handler
log_handler = LogHandler()
logging.getLogger("trilium-alchemy").addHandler(log_handler)

runner = CliRunner()


def test_check():
    # use subprocess to verify "trilium-alchemy" is available as a command
    subprocess.check_call(["trilium-alchemy", "check"])


def test_config(request: FixtureRequest, session: Session, tmp_path: Path):
    config_path = tmp_path / "test-config.yaml"
    root_data_dir = tmp_path / "root-data-dir"

    root_data_dir.mkdir()

    test_instance_data_dir = root_data_dir / "test-instance"
    test_instance_data_dir.mkdir()

    # explicitly set this one
    bad_instance_data_dir = root_data_dir / "test-instance-data"
    bad_instance_data_dir.mkdir()

    # generate a config file dynamically with connection info
    model = Config(
        root_data_dir=root_data_dir,
        instances={
            "test-instance": InstanceConfig(
                host=session.host, token=session._token
            ),
            "bad-instance": InstanceConfig(
                host=session.host,
                token="bad_token",
                data_dir=bad_instance_data_dir,
            ),
        },
    )
    model.dump_yaml(config_path)

    # test connection using config file
    _run(
        request,
        [
            "--instance",
            "test-instance",
            "--config-file",
            config_path,
            "check",
        ],
    )

    # do a dummy database restore to verify data dirs
    dummy_db = tmp_path / "dummy-document.db"
    dummy_db.write_bytes(b"")

    _run(
        request,
        [
            "--instance",
            "test-instance",
            "--config-file",
            config_path,
            "db",
            "restore",
            "-y",
            dummy_db,
        ],
    )
    assert (test_instance_data_dir / "document.db").is_file()

    _run(
        request,
        [
            "--instance",
            "bad-instance",
            "--config-file",
            config_path,
            "db",
            "restore",
            "-y",
            dummy_db,
        ],
    )
    assert (bad_instance_data_dir / "document.db").is_file()

    # missing instance in config file
    _run(
        request,
        [
            "--instance",
            "nonexistent-instance",
            "--config-file",
            config_path,
            "check",
        ],
        2,
    )

    # bad instance in config file (bad token)
    _run(
        request,
        [
            "--instance",
            "bad-instance",
            "--config-file",
            config_path,
            "check",
        ],
        1,
    )

    # nonexistent config file
    _run(
        request,
        [
            "--instance",
            "nonexistent",
            "--config-file",
            "nonexistent.yaml",
            "check",
        ],
        2,
    )

    # invalid config file
    invalid_config_path = tmp_path / "test-invalid-config.yaml"
    invalid_config_path.write_text("")
    _run(
        request,
        [
            "--instance",
            "nonexistent",
            "--config-file",
            invalid_config_path,
            "check",
        ],
        2,
    )


def test_db(
    request: FixtureRequest,
    session: Session,
    tmp_path: Path,
    skip_teardown: bool,
):
    if skip_teardown:
        skip("Expects an empty tree")

    # create a test note
    assert len(session.root.children) == 0
    session.root += Note("test note", session=session)
    session.flush()

    # backup with specific name and verify
    now = (
        str(datetime.datetime.now())
        .replace(" ", "_")
        .replace(":", "-")
        .replace(".", "-")
    )
    now_path = BACKUP_PATH / f"backup-{now}.db"
    assert not now_path.is_file()

    _run(request, ["db", "backup", "--name", now, "--verify"])
    assert now_path.is_file()
    now_path.unlink()

    # backup with auto-name
    _run(request, ["db", "backup", "--auto-name"])

    # get generated name from logs
    auto_name_log = log_handler.test_logs[-1]
    match = re.search(r"Wrote backup: '(.*)'", auto_name_log)
    assert match
    assert len(match.groups()) == 1

    backup_name = str(match.group(1))
    backup_path = BACKUP_PATH / backup_name

    print(f"Got --auto-name backup path: {backup_path}")
    assert backup_path.is_file()

    # backup to folder w/file having unique name
    _run(request, ["db", "backup", "--dest", tmp_path])

    # backup to specific file
    backup_path = tmp_path / "test.db"
    _run(request, ["db", "backup", "--dest", backup_path])

    # attempt to backup to same file
    _run(request, ["db", "backup", "--dest", backup_path], 2)

    # backup to same file, overwriting it
    _run(request, ["db", "backup", "--dest", backup_path, "--overwrite"])

    # attempt to backup to nonexistent folder
    _run(
        request,
        [
            "db",
            "backup",
            "--dest",
            tmp_path / "nonexistent_dir" / "nonexistent.db",
        ],
        2,
    )

    # add another note to root
    session.root += Note("test note 2", session=session)
    session.flush()

    def restore():
        assert DB_PATH.is_file()
        DB_PATH.unlink()
        assert not DB_PATH.exists()

        # test dry run
        _run(request, ["db", "restore", "--dry-run", backup_path])
        assert not DB_PATH.exists()

        # actually restore
        _run(request, ["db", "restore", "-y", backup_path])
        assert DB_PATH.is_file()

    _restart_trilium(restore)

    # ensure trilium started up again and database is restored with only 1 note
    session2 = Session(host=HOST, token=TOKEN, default=False)
    assert len(session2.root.children) == 1
    assert session2.root.children[0].title == "test note"

    # attempt to restore a nonexistent file
    _run(request, ["db", "restore", tmp_path / "nonexistent.db"], 2)

    # cleanup
    session2.root.children[0].delete()
    session2.flush()


def test_tree(
    request: FixtureRequest,
    session: Session,
    tmp_path: Path,
    skip_teardown: bool,
):
    if skip_teardown:
        skip("Expects an empty tree")

    # create a test note
    assert len(session.root.children) == 0
    note = Note("test note", session=session)
    note.labels.set_value("testLabel", "testValue")
    note ^= session.root
    note += Note("test note 2", session=session)

    session.flush()
    assert len(session.root.children) == 1

    # export root
    root_path = tmp_path / "root.zip"
    _run(request, ["tree", "export", root_path])
    assert root_path.is_file()

    # export by label
    label_path = tmp_path / "label.zip"
    _run(request, ["tree", "--search", "#testLabel", "export", label_path])
    assert label_path.is_file()

    # attempt to export to same file
    _run(request, ["tree", "export", root_path], 2)

    # export to same file, overwriting it
    _run(request, ["tree", "export", "--overwrite", root_path])

    # delete note
    note.delete()
    session.flush()
    assert len(session.root.children) == 0

    # import root
    _run(request, ["tree", "import", root_path])

    session.root.refresh()
    assert len(session.root.children) == 1
    note = session.root.children[0]

    assert note.title == "test note"
    assert note.labels.get_value("testLabel") == "testValue"
    assert len(note.children) == 1
    assert note.children[0].title == "test note 2"
    note.children[0].delete()
    session.flush()
    assert len(note.children) == 0

    # import by label
    _run(request, ["tree", "--search", "#testLabel", "import", label_path])

    note.refresh()
    assert len(note.children) == 1
    assert len(note.children[0].children)
    assert note.children[0].title == "test note"
    assert note.children[0].children[0].title == "test note 2"

    # attempt to import by label with multiple labels
    _run(request, ["tree", "--search", "#testLabel", "import", label_path], 2)

    # attempt to import a nonexistent file
    _run(request, ["tree", "import", tmp_path / "nonexistent.zip"], 2)

    # cleanup
    note.delete()
    session.flush()
    assert len(session.root.children) == 0


def test_fs(
    request: FixtureRequest, session: Session, note: Note, tmp_path: Path
):
    # add a label to parent note so we can search for it later
    note["note1_parent"] = ""

    note_1 = create_note_1(session, note)
    session.flush()

    # dump with dry run
    _run(request, ["fs", "dump", "--note-id", NOTE_1_ID, "--dry-run", tmp_path])
    assert next(tmp_path.iterdir(), None) is None

    # dump and compare
    _run(request, ["fs", "dump", "--note-id", NOTE_1_ID, tmp_path])
    compare_folders(tmp_path, TREE_DUMP_PATH)

    # load and ensure no changes were made
    _run(request, ["fs", "load", tmp_path])
    assert log_handler.test_logs[-1] == "No changes to commit"

    # delete and then load
    note_1.delete()
    session.flush()

    # ensure load with no parents fails
    _run(request, ["fs", "load", "-y", tmp_path], 1)

    # load with parent
    _run(
        request,
        ["fs", "load", "--parent-search", "#note1_parent", "-y", tmp_path],
    )

    # load again and ensure no changes were made
    _run(request, ["fs", "load", tmp_path])
    assert log_handler.test_logs[-1] == "No changes to commit"

    note_1_path = _map_note_dir(note_1)
    content_file = tmp_path / note_1_path / "content.txt"

    orig_content = content_file.read_text()
    updated_content = "Updated content"

    # manually modify content for note 1
    content_file.write_text(updated_content)

    # scan content to update metadata, dry run first
    _run(request, ["fs", "scan", "--dry-run", tmp_path])
    assert content_file.read_text() == updated_content

    _run(request, ["fs", "scan", tmp_path])

    # dump again, content should be updated
    _run(request, ["fs", "dump", "--note-id", NOTE_1_ID, tmp_path])
    assert content_file.read_text() == orig_content
    compare_folders(tmp_path, TREE_DUMP_PATH)


def test_note_sync_template(
    request: FixtureRequest, session: Session, note: Note
):
    def modify_template(template: Note):
        """
        Add a child note to this template.
        """
        template += Note(
            f"{template.title} - Child {len(template.children) + 1}",
            session=session,
        )
        session.flush()

    def check_instance(instance: Note, template: Note, same: bool = True):
        """
        Ensure instance is in sync with template.
        """
        # pick up changes from CLI
        instance.refresh()

        if same:
            assert len(instance.children) == len(template.children)
            for instance_child, template_child in zip(
                iter(instance.children), iter(template.children)
            ):
                assert instance_child.title == template_child.title
        else:
            assert len(instance.children) != len(template.children)

    # create templates
    template1 = Note("Test template", session=session)
    template1["template"] = ""
    template1["template1"] = ""
    template2 = Note("Test workspace template", session=session)
    template2["workspaceTemplate"] = ""
    template2["template2"] = ""
    template3 = Note("Test template 3", session=session)
    template3["template"] = ""

    note += [template1, template2, template3]
    session.flush()

    # test no notes matching any template
    _run(request, ["note", "sync-template", "-y"])

    # create template instances
    inst1 = Note("Instance 1", template=template1, session=session)
    inst1["inst1"] = ""
    inst2 = Note("Instance 2", template=template2, session=session)
    inst2["inst2"] = ""

    note += [inst1, inst2]
    session.flush()

    def modify_templates():
        modify_template(template1)
        modify_template(template2)

    def check_instances(same_inst1: bool = True, same_inst2: bool = True):
        check_instance(inst1, template1, same=same_inst1)
        check_instance(inst2, template2, same=same_inst2)

    # sync notes matching any template
    modify_templates()
    _run(request, ["note", "sync-template", "-y"])
    check_instances()

    # sync template1 by template search
    modify_templates()
    _run(
        request,
        [
            "note",
            "sync-template",
            "--template-search",
            "#template #template1",
            "-y",
        ],
    )
    check_instances(True, False)

    # sync inst2 by note search
    modify_templates()
    _run(request, ["note", "--search", "#inst2", "sync-template", "-y"])
    check_instances(False, True)

    # sync both instances again
    _run(request, ["note", "sync-template", "-y"])
    check_instances()

    # attempt to sync inst1 with template2
    _run(
        request,
        [
            "note",
            "--note-id",
            inst1.note_id,
            "sync-template",
            "--template-note-id",
            template2.note_id,
            "-y",
        ],
    )

    # sync note which does not have any template
    _run(
        request,
        ["note", "--note-id", note.note_id, "sync-template", "-y"],
    )

    # sync template without any instances
    _run(
        request,
        [
            "note",
            "sync-template",
            "--template-note-id",
            template3.note_id,
            "-y",
        ],
    )

    # sync invalid template
    _run(
        request,
        ["note", "sync-template", "--template-note-id", inst1.note_id, "-y"],
        1,
    )

    # sync nonexistent template
    _run(
        request,
        ["note", "sync-template", "--template-note-id", "nonexistent_id", "-y"],
        2,
    )
    _run(
        request,
        [
            "note",
            "sync-template",
            "--template-search",
            "#nonexistent_label",
            "-y",
        ],
        2,
    )

    # sync nonexistent note
    _run(
        request,
        ["note", "--note-id", "nonexistent_id", "sync-template", "-y"],
        2,
    )
    _run(
        request,
        ["note", "--search", "#nonexistent_label", "sync-template", "-y"],
        2,
    )


def test_note_cleanup_positions(
    request: FixtureRequest, session: Session, note: Note
):
    # create child note to verify recursion
    child = Note("Test child", session=session)
    child ^= note
    session.flush()

    create_label(session.api, note, "label1", "value1", 1)
    create_label(session.api, note, "label2", "value2", 3)
    create_label(session.api, note, "label3", "value3", 10)

    create_label(session.api, child, "child_label1", "value1", 1)
    create_label(session.api, child, "child_label2", "value2", 2)
    create_label(session.api, child, "child_label3", "value3", 3)

    note.refresh()
    child.refresh()
    assert session.dirty_count == 0

    label1, label2, label3 = note.labels.owned
    child_label1, child_label2, child_label3 = child.labels.owned

    assert label1.position == 1
    assert label2.position == 3
    assert label3.position == 10
    assert child_label1.position == 1
    assert child_label2.position == 2
    assert child_label3.position == 3

    # run command to cleanup positions without recursing
    _run(request, ["note", "--search", "#label1", "cleanup-positions", "-y"])

    # refresh notes and check
    note.refresh()
    child.refresh()
    assert session.dirty_count == 0

    assert label1.position == 10
    assert label2.position == 20
    assert label3.position == 30
    assert child_label1.position == 1
    assert child_label2.position == 2
    assert child_label3.position == 3

    # run command to cleanup positions with recursing
    _run(
        request,
        [
            "note",
            "--search",
            "#label1",
            "--recurse",
            "cleanup-positions",
            "-y",
        ],
    )

    # refresh notes and check
    note.refresh()
    child.refresh()
    assert session.dirty_count == 0

    assert label1.position == 10
    assert label2.position == 20
    assert label3.position == 30
    assert child_label1.position == 10
    assert child_label2.position == 20
    assert child_label3.position == 30


def _restart_trilium(callable: Callable[[], None]):
    """
    Restart Trilium using docker, invoking the provided callback while shutdown.
    """

    # shutdown trilium
    subprocess.check_call(["docker-compose", "down"])

    # invoke callable
    callable()

    # start trilium
    subprocess.check_call(["docker-compose", "up", "-d"])

    # wait for trilium to startup
    time.sleep(5)


def _run(
    request: FixtureRequest,
    cmd: list[str | Path],
    exit_code: int = 0,
):
    """
    Run command and verify exit code.
    """

    cmd_norm = _normalize_cmd(cmd)
    print_stdout = bool(request.config.getoption("--cli-stdout"))

    if print_stdout:
        print(DIVIDER)
        print(f"$ trilium-alchemy {_get_shell_cmd(cmd_norm)}")

    # invoke command
    result = runner.invoke(app, args=cmd_norm, catch_exceptions=False)

    if print_stdout:
        print(result.stdout.strip())
        print(DIVIDER)

    assert result.exit_code == exit_code


def _normalize_cmd(cmd: list[str | Path]) -> list[str]:
    return [str(c) for c in cmd]


def _get_shell_cmd(cmd: list[str]) -> str:
    """
    Get command in the form it could be run in a shell, including required
    quotes.
    """
    return " ".join(f'"{c}"' if " " in c else c for c in cmd)
