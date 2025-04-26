import datetime
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from pytest import raises

from trilium_alchemy import *

from .conftest import BACKUP_PATH, DB_PATH, HOST, TOKEN

MAIN_CMD = ["trilium-alchemy"]
DB_CMD = MAIN_CMD + ["db"]
TREE_CMD = MAIN_CMD + ["tree"]


def test_db(session: Session, tmp_path: Path):
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

    _run(DB_CMD + ["backup", "--name", now, "--verify"])
    assert now_path.is_file()
    now_path.unlink()

    # backup with auto-name
    output = _run_output(DB_CMD + ["backup", "--auto-name"])
    match = re.search(r"Wrote backup: '(.*)'", output)
    assert match
    assert len(match.groups()) == 1
    backup_name = str(match.group(1))
    backup_path = BACKUP_PATH / backup_name

    print(f"Got --auto-name backup path: {backup_path}")
    assert backup_path.is_file()

    # backup to folder w/file having unique name
    _run(DB_CMD + ["backup", "--dest", tmp_path])

    # backup to specific file
    backup_path = tmp_path / "test.db"
    _run(DB_CMD + ["backup", "--dest", backup_path])

    # attempt to backup to same file
    with raises(subprocess.CalledProcessError):
        try:
            _run(DB_CMD + ["backup", "--dest", backup_path])
        except subprocess.CalledProcessError as e:
            assert e.returncode == 2
            raise

    # backup to same file, overwriting it
    _run(DB_CMD + ["backup", "--dest", backup_path, "--overwrite"])

    # add another note to root
    session.root += Note("test note 2", session=session)
    session.flush()

    def restore():
        assert DB_PATH.is_file()
        DB_PATH.unlink()
        assert not DB_PATH.exists()

        # test dry run
        _run(DB_CMD + ["restore", "--dry-run", backup_path])
        assert not DB_PATH.exists()

        # actually restore
        _run(DB_CMD + ["restore", "-y", backup_path])
        assert DB_PATH.is_file()

    _restart_trilium(restore)

    # ensure trilium started up again and database is restored with only 1 note
    session2 = Session(host=HOST, token=TOKEN, default=False)
    assert len(session2.root.children) == 1
    assert session2.root.children[0].title == "test note"

    # attempt to restore a nonexistent file
    with raises(subprocess.CalledProcessError):
        try:
            _run(DB_CMD + ["restore", tmp_path / "nonexistent.db"])
        except subprocess.CalledProcessError as e:
            assert e.returncode == 2
            raise

    # cleanup
    session2.root.children[0].delete()
    session2.flush()


def test_tree(session: Session, tmp_path: Path):
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
    _run(TREE_CMD + ["export", root_path])
    assert root_path.is_file()

    # export by label
    label_path = tmp_path / "label.zip"
    _run(TREE_CMD + ["--search", "#testLabel", "export", label_path])
    assert label_path.is_file()

    # attempt to export to same file
    with raises(subprocess.CalledProcessError):
        try:
            _run(TREE_CMD + ["export", root_path])
        except subprocess.CalledProcessError as e:
            assert e.returncode == 2
            raise

    # export to same file, overwriting it
    _run(TREE_CMD + ["export", "--overwrite", root_path])

    # delete note
    note.delete()
    session.flush()
    assert len(session.root.children) == 0

    # import root
    _run(TREE_CMD + ["import", root_path])

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
    _run(TREE_CMD + ["--search", "#testLabel", "import", label_path])

    note.refresh()
    assert len(note.children) == 1
    assert len(note.children[0].children)
    assert note.children[0].title == "test note"
    assert note.children[0].children[0].title == "test note 2"

    # attempt to import by label with multiple labels
    with raises(subprocess.CalledProcessError):
        try:
            _run(TREE_CMD + ["--search", "#testLabel", "import", label_path])
        except subprocess.CalledProcessError as e:
            assert e.returncode == 2
            raise

    # attempt to import a nonexistent file
    with raises(subprocess.CalledProcessError):
        try:
            _run(TREE_CMD + ["import", tmp_path / "nonexistent.zip"])
        except subprocess.CalledProcessError as e:
            assert e.returncode == 2
            raise

    # cleanup
    note.delete()
    session.flush()
    assert len(session.root.children) == 0


def _restart_trilium(callable: Callable[[], None]):
    """
    Restart Trilium using docker, invoking the provided callback while shutdown.
    """

    # shutdown trilium
    _run(["docker-compose", "down"])

    # invoke callable
    callable()

    # start trilium
    _run(["docker-compose", "up", "-d"])

    # wait for trilium to startup
    time.sleep(5)


def _run(cmd: list[str]):
    print(f"Running: {cmd}")
    subprocess.check_call(cmd)


def _run_output(cmd: list[str]) -> str:
    print(f"Running: {cmd}")
    return subprocess.check_output(cmd, text=True)
