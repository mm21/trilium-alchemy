import datetime
import logging
import os
import shutil
from pathlib import Path

from click import BadParameter, UsageError
from typer import Argument, Context, Option

from ._utils import OperationTyper, get_operation_params, lookup_param

MAX_BACKUP_TIME_DELTA = 5
"""
Maximum number of seconds within which the backup should have been created
by Trilium.
"""


app = OperationTyper(
    "db",
    help="Database maintenance operations",
)


@app.command(require_session=True, require_data_dir=True)
def backup(
    ctx: Context,
    path: Path = Argument(
        help="Destination database file or folder; if folder, filename will be generated using current datetime"
    ),
    name: str = Option(
        "now",
        help="Name of backup in Trilum data dir to generate, e.g. 'now' will write 'backup-now.db'",
    ),
    overwrite: bool = Option(
        False, help="Whether to overwrite destination file if it already exists"
    ),
):
    """
    Backup database to file
    """
    params = get_operation_params(ctx)
    assert params.session
    assert params.trilium_data_dir

    # ensure destination folder exists
    if not path.is_dir():
        # assume path is a specific file in a folder
        if not path.parent.is_dir():
            raise BadParameter(
                f"Destination '{path}' is neither a folder nor a child of an existing folder",
                ctx=ctx,
                param=lookup_param(ctx, "path"),
            )

    # get formatted current time
    now = datetime.datetime.now().strftime(r"%Y-%m-%d_%H-%M-%S")

    # get source/destination path
    src_path = params.trilium_data_dir / "backup" / f"backup-{name}.db"
    dst_path = path / f"backup-{now}.db" if path.is_dir() else path

    # ensure destination path is allowed to be overwritten if it exists
    if dst_path.exists() and not overwrite:
        raise UsageError(
            f"Destination '{dst_path}' exists and --overwrite was not passed",
            ctx=ctx,
        )

    # create backup
    params.session.backup(name)

    # validate that trilium created the backup
    assert (
        src_path.is_file()
    ), f"Trilium failed to create backup at '{src_path}'"

    mod_time = os.path.getmtime(src_path)
    mod_datetime = datetime.datetime.fromtimestamp(mod_time)

    delta = (datetime.datetime.now() - mod_datetime).seconds
    assert (
        delta <= MAX_BACKUP_TIME_DELTA
    ), f"Backup '{src_path}' was written {delta} seconds ago, which is more than the expected maximum of {MAX_BACKUP_TIME_DELTA}"

    # copy backup to destination
    shutil.copyfile(src_path, dst_path)

    logging.info(f"Wrote backup: '{src_path}' -> '{dst_path}'")


@app.command(require_data_dir=True)
def restore(
    ctx: Context,
    path: Path = Argument(help="Source database file"),
):
    """
    Restore database from file
    """
    params = get_operation_params(ctx)
    assert params.trilium_data_dir

    if not path.is_file():
        raise BadParameter(
            f"Source database '{path}' does not exist",
            ctx=ctx,
            param=lookup_param(ctx, "path"),
        )

    dst_path = params.trilium_data_dir / "document.db"

    # copy backup to database in trilium data dir
    shutil.copyfile(path, dst_path)

    logging.info(f"Restored backup: '{path}' -> '{dst_path}'")
