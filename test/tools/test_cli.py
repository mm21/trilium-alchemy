import datetime
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from pytest import skip
from typer.testing import CliRunner

from trilium_alchemy import *
from trilium_alchemy.tools.cli.main import app
from trilium_alchemy.tools.config import Config, InstanceConfig

from ..conftest import (
    BACKUP_PATH,
    DB_PATH,
    HOST,
    TOKEN,
    compare_folders,
    create_label,
)
from .fs_utils import NOTE_1_ID, TREE_DUMP_PATH, create_note_1


class LogHandler(logging.Handler):
    test_logs: list[str]

    def __init__(self):
        super().__init__()
        self.test_logs = []

    def emit(self, record: logging.LogRecord):
        self.test_logs.append(record.message)


# register handler so we can get access to recent logs for verification
log_handler = LogHandler()
logging.getLogger().addHandler(log_handler)

runner = CliRunner()


def test_check():
    # use subprocess to verify "trilium-alchemy" is available as a command
    subprocess.check_call(["trilium-alchemy", "check"])


def test_config(session: Session, tmp_path: Path):
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
        [
            "--instance",
            "test-instance",
            "--config-file",
            config_path,
            "check",
        ]
    )

    # do a dummy database restore to verify data dirs
    dummy_db = tmp_path / "dummy-document.db"
    dummy_db.write_bytes(b"")

    _run(
        [
            "--instance",
            "test-instance",
            "--config-file",
            config_path,
            "db",
            "restore",
            "-y",
            dummy_db,
        ]
    )
    assert (test_instance_data_dir / "document.db").is_file()

    _run(
        [
            "--instance",
            "bad-instance",
            "--config-file",
            config_path,
            "db",
            "restore",
            "-y",
            dummy_db,
        ]
    )
    assert (bad_instance_data_dir / "document.db").is_file()

    # missing instance in config file
    _run(
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
        [
            "--instance",
            "bad-instance",
            "--config-file",
            config_path,
            "check",
        ],
        1,
        log_level=logging.CRITICAL,
    )

    # nonexistent config file
    _run(
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
        [
            "--instance",
            "nonexistent",
            "--config-file",
            invalid_config_path,
            "check",
        ],
        2,
    )


def test_db(session: Session, tmp_path: Path, skip_teardown: bool):
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

    _run(["db", "backup", "--name", now, "--verify"])
    assert now_path.is_file()
    now_path.unlink()

    # backup with auto-name, setting log level so we get the info log
    _run(["db", "backup", "--auto-name"], log_level=logging.INFO)

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
    _run(["db", "backup", "--dest", tmp_path])

    # backup to specific file
    backup_path = tmp_path / "test.db"
    _run(["db", "backup", "--dest", backup_path])

    # attempt to backup to same file
    _run(["db", "backup", "--dest", backup_path], 2)

    # backup to same file, overwriting it
    _run(["db", "backup", "--dest", backup_path, "--overwrite"])

    # add another note to root
    session.root += Note("test note 2", session=session)
    session.flush()

    def restore():
        assert DB_PATH.is_file()
        DB_PATH.unlink()
        assert not DB_PATH.exists()

        # test dry run
        _run(["db", "restore", "--dry-run", backup_path])
        assert not DB_PATH.exists()

        # actually restore
        _run(["db", "restore", "-y", backup_path])
        assert DB_PATH.is_file()

    _restart_trilium(restore)

    # ensure trilium started up again and database is restored with only 1 note
    session2 = Session(host=HOST, token=TOKEN, default=False)
    assert len(session2.root.children) == 1
    assert session2.root.children[0].title == "test note"

    # attempt to restore a nonexistent file
    _run(["db", "restore", tmp_path / "nonexistent.db"], 2)

    # cleanup
    session2.root.children[0].delete()
    session2.flush()


def test_tree(session: Session, tmp_path: Path, skip_teardown: bool):
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
    _run(["tree", "export", root_path])
    assert root_path.is_file()

    # export by label
    label_path = tmp_path / "label.zip"
    _run(["tree", "--search", "#testLabel", "export", label_path])
    assert label_path.is_file()

    # attempt to export to same file
    _run(["tree", "export", root_path], 2)

    # export to same file, overwriting it
    _run(["tree", "export", "--overwrite", root_path])

    # delete note
    note.delete()
    session.flush()
    assert len(session.root.children) == 0

    # import root
    _run(["tree", "import", root_path])

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
    _run(["tree", "--search", "#testLabel", "import", label_path])

    note.refresh()
    assert len(note.children) == 1
    assert len(note.children[0].children)
    assert note.children[0].title == "test note"
    assert note.children[0].children[0].title == "test note 2"

    # attempt to import by label with multiple labels
    _run(["tree", "--search", "#testLabel", "import", label_path], 2)

    # attempt to import a nonexistent file
    _run(["tree", "import", tmp_path / "nonexistent.zip"], 2)

    # cleanup
    note.delete()
    session.flush()
    assert len(session.root.children) == 0


def test_fs(session: Session, note: Note, tmp_path: Path):
    # add a label to parent note so we can search for it later
    note["note1_parent"] = ""

    note_1 = create_note_1(session, note)
    session.flush()

    # dump with dry run
    _run(["fs", "dump", "--note-id", NOTE_1_ID, "--dry-run", tmp_path])
    assert next(tmp_path.iterdir(), None) is None

    # dump and compare
    _run(["fs", "dump", "--note-id", NOTE_1_ID, tmp_path])
    compare_folders(tmp_path, TREE_DUMP_PATH)

    # load and ensure no changes were made
    _run(["fs", "load", tmp_path], log_level=logging.INFO)
    assert log_handler.test_logs[-1] == "No changes to commit"

    # delete and then load
    note_1.delete()
    session.flush()

    # ensure load with no parents fails (no need for error in test logs)
    _run(["fs", "load", "-y", tmp_path], 1, log_level=logging.CRITICAL)

    # load with parent
    _run(["fs", "load", "--parent-search", "#note1_parent", "-y", tmp_path])

    # load again and ensure no changes were made
    _run(["fs", "load", tmp_path], log_level=logging.INFO)
    assert log_handler.test_logs[-1] == "No changes to commit"


def test_note(session: Session, note: Note):
    create_label(session.api, note, "label1", "value1", 1)
    create_label(session.api, note, "label2", "value2", 3)
    create_label(session.api, note, "label3", "value3", 10)

    note.refresh()
    assert len(note.labels.owned) == 3
    assert session.dirty_count == 0

    label1, label2, label3 = note.labels.owned

    assert label1.position == 1
    assert label2.position == 3
    assert label3.position == 10

    # run command to cleanup positions
    _run(["note", "--search", "#label1", "cleanup-positions", "-y"])

    # refresh note and check
    note.refresh()
    assert session.dirty_count == 0

    assert label1.position == 10
    assert label2.position == 20
    assert label3.position == 30


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
    cmd: list[str | Path], exit_code: int = 0, log_level: int | None = None
):
    """
    Run command and verify exit code.
    """
    cmd_norm = _normalize_cmd(cmd)
    print(f"Running: trilium-alchemy {' '.join(cmd_norm)}")

    # backup/restore log level if applicable
    prev_log_level = (
        logging.getLogger().level if log_level is not None else None
    )
    if log_level is not None:
        logging.getLogger().setLevel(log_level)

    # invoke command
    result = runner.invoke(app, args=cmd_norm, catch_exceptions=False)

    if prev_log_level is not None:
        logging.getLogger().setLevel(prev_log_level)

    assert result.exit_code == exit_code


def _normalize_cmd(cmd: list[str | Path]) -> list[str]:
    return [str(c) for c in cmd]
