import subprocess
import time
from pathlib import Path

from pytest import raises

from trilium_alchemy import *

from .conftest import HOST, TOKEN

DB_CMD = ["trilium-alchemy", "db"]


def test_db_backup(tmp_path: Path):
    # backup to folder w/unique source
    subprocess.check_call(DB_CMD + ["backup", str(tmp_path)])

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


def test_db_restore(tmp_path: Path):
    # create a test note in db
    session = Session(host=HOST, token=TOKEN, default=False)
    assert len(session.root.children) == 0
    session.root += Note("test note", session=session)
    session.flush()

    # backup to specific file
    backup_path = tmp_path / "test.db"
    subprocess.check_call(DB_CMD + ["backup", backup_path])

    # shutdown trilium before restoring
    subprocess.check_call(["docker-compose", "down"])

    # restore
    subprocess.check_call(DB_CMD + ["restore", str(backup_path)])

    # start trilium again
    subprocess.check_call(["docker-compose", "up", "-d"])

    # wait for trilium to startup
    time.sleep(5)

    # ensure trilium started up again
    session2 = Session(host=HOST, token=TOKEN, default=False)
    assert len(session2.root.children) == 1
    assert session2.root.children[0].title == "test note"

    # cleanup
    session2.root.children[0].delete()
    session2.flush()
