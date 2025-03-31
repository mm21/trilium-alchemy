import subprocess
import time
from pathlib import Path
from typing import Callable

from pytest import raises

from trilium_alchemy import *

from .conftest import DATA_DIR, HOST, TOKEN

MAIN_CMD = ["trilium-alchemy"]
DB_CMD = MAIN_CMD + ["db"]
TREE_CMD = MAIN_CMD + ["tree"]


def test_db(session: Session, tmp_path: Path):
    # create a test note
    assert len(session.root.children) == 0
    session.root += Note("test note", session=session)
    session.flush()

    # backup to folder w/unique name
    subprocess.check_call(DB_CMD + ["backup", tmp_path])

    # backup to specific file
    backup_path = tmp_path / "test.db"
    subprocess.check_call(DB_CMD + ["backup", backup_path])

    # attempt to backup to same file
    with raises(subprocess.CalledProcessError):
        try:
            subprocess.check_call(DB_CMD + ["backup", backup_path])
        except subprocess.CalledProcessError as e:
            assert e.returncode == 2
            raise

    # backup to same file, overwriting it
    subprocess.check_call(DB_CMD + ["backup", "--overwrite", backup_path])

    # add another note to root
    session.root += Note("test note 2", session=session)
    session.flush()

    db_path = DATA_DIR / "document.db"

    def restore():
        assert db_path.is_file()
        db_path.unlink()
        assert not db_path.exists()
        subprocess.check_call(DB_CMD + ["restore", backup_path])
        assert db_path.is_file()

    _restart_trilium(restore)

    # ensure trilium started up again and database is restored with only 1 note
    session2 = Session(host=HOST, token=TOKEN, default=False)
    assert len(session2.root.children) == 1
    assert session2.root.children[0].title == "test note"

    # attempt to restore a nonexistent file
    with raises(subprocess.CalledProcessError):
        try:
            subprocess.check_call(
                DB_CMD + ["restore", tmp_path / "nonexistent.db"]
            )
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
    root_path = tmp_path / "test.zip"
    subprocess.check_call(TREE_CMD + ["export", root_path])
    assert root_path.is_file()

    # export by label
    label_path = tmp_path / "label.zip"
    subprocess.check_call(
        TREE_CMD + ["export", "--label", "testLabel", label_path]
    )
    assert label_path.is_file()

    # attempt to export to same file
    with raises(subprocess.CalledProcessError):
        try:
            subprocess.check_call(TREE_CMD + ["export", root_path])
        except subprocess.CalledProcessError as e:
            assert e.returncode == 2
            raise

    # export to same file, overwriting it
    subprocess.check_call(TREE_CMD + ["export", "--overwrite", root_path])

    # delete note
    note.delete()
    session.flush()
    assert len(session.root.children) == 0

    # import root
    subprocess.check_call(TREE_CMD + ["import", root_path])

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
    subprocess.check_call(
        TREE_CMD + ["import", "--label", "testLabel", label_path]
    )

    note.refresh()
    assert len(note.children) == 1
    assert len(note.children[0].children)
    assert note.children[0].title == "test note"
    assert note.children[0].children[0].title == "test note 2"

    # attempt to import by label with multiple labels
    with raises(subprocess.CalledProcessError):
        try:
            subprocess.check_call(
                TREE_CMD + ["import", "--label", "testLabel", label_path]
            )
        except subprocess.CalledProcessError as e:
            assert e.returncode == 2
            raise

    # attempt to import a nonexistent file
    with raises(subprocess.CalledProcessError):
        try:
            subprocess.check_call(
                TREE_CMD + ["import", tmp_path / "nonexistent.zip"]
            )
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
    subprocess.check_call(["docker-compose", "down"])

    # invoke callable
    callable()

    # start trilium
    subprocess.check_call(["docker-compose", "up", "-d"])

    # wait for trilium to startup
    time.sleep(5)
