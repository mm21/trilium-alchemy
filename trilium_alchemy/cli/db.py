import datetime
import logging
import os
import shutil
from pathlib import Path

from click import Abort, BadParameter, UsageError
from typer import Argument, Context, Option

from ._utils import OperationTyper, get_operation_params

MAX_BACKUP_TIME_DELTA = 10
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
    overwrite: bool = Option(
        False, help="Whether to overwrite destination file if it already exists"
    ),
    unique: bool = Option(
        False,
        help="Whether the backup in Trilium data dir should have a unique filename based on current timestamp instead of 'now.db'",
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
                param=ctx.params.get("path"),
            )

    # get formatted current time
    now = datetime.datetime.now().strftime(r"%Y-%m-%d_%H-%M-%S")

    # get name of backup file in trilium data dir
    backup_name = now if unique else "now"

    # get source/destination path
    src_path = params.trilium_data_dir / "backup" / f"backup-{backup_name}.db"
    dest_path = path / f"{now}.db" if path.is_dir() else path

    # ensure destination path is allowed to be overwritten if it exists
    if dest_path.exists():
        if not overwrite:
            raise UsageError(
                f"Destination '{dest_path}' exists and --overwrite was not passed",
                ctx=ctx,
            )

    # create backup
    params.session.backup(backup_name)

    # validate that trilium created the backup
    if not src_path.is_file():
        raise Abort(f"Trilium failed to create backup '{src_path}'")

    mod_time = os.path.getmtime(src_path)
    mod_datetime = datetime.datetime.fromtimestamp(mod_time)

    if (
        delta := (datetime.datetime.now() - mod_datetime).seconds
    ) > MAX_BACKUP_TIME_DELTA:
        raise Abort(
            f"Backup '{src_path}' was written {delta} seconds ago, which is more than the expected maximum of {MAX_BACKUP_TIME_DELTA}"
        )

    # copy backup to destination
    shutil.copyfile(src_path, dest_path)

    logging.info(f"Wrote backup to '{dest_path}'")


@app.command(require_data_dir=True)
def restore(
    ctx: Context,
    path: Path = Argument(help="Source database file"),
):
    """
    Restore database from file
    """
    params = get_operation_params(ctx)
    print(f"--- got params: {params}")
