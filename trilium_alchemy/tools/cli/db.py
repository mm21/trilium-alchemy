import datetime
import logging
import os
import shutil
from pathlib import Path

from click import BadParameter, ClickException
from typer import Argument, Context, Option

from ._utils import MainTyper, get_root_context, lookup_param

MAX_BACKUP_TIME_DELTA = 5
"""
Maximum number of seconds within which the backup should have been created
by Trilium.
"""


app = MainTyper(
    "db",
    help="Database maintenance operations",
)


@app.command()
def backup(
    ctx: Context,
    name: str = Option(
        "now",
        help="Name of backup in Trilium data dir to generate, e.g. 'now' will write 'backup-now.db'",
    ),
    auto_name: bool = Option(
        False,
        "--auto-name",
        help="Whether to use current datetime as name instead of --name option",
    ),
    verify: bool = Option(
        False, "--verify", help="Whether to verify by checking backup's mtime"
    ),
    dest: Path
    | None = Option(
        None,
        help="Optional destination database file or folder to copy backup; if folder, filename will use current datetime",
    ),
    overwrite: bool = Option(
        False,
        "--overwrite",
        help="Whether to overwrite destination file if it already exists",
    ),
):
    """
    Backup database, optionally copying to destination path
    """

    now = datetime.datetime.now().strftime(r"%Y-%m-%d_%H-%M-%S")

    # select name
    backup_name = now if auto_name else name

    # normalize destination, if any
    if dest:
        dest_path = dest / f"backup-{now}.db" if dest.is_dir() else dest

        # ensure destination path is allowed to be overwritten if it exists
        if dest_path.exists() and not overwrite:
            raise BadParameter(
                f"destination '{dest_path}' exists and --overwrite was not passed",
                ctx=ctx,
                param=lookup_param(ctx, "dest"),
            )
    else:
        dest_path = None

    # determine whether data dir is required
    require_data_dir = bool(dest or verify)

    root_context = get_root_context(ctx, require_data_dir=require_data_dir)
    data_dir = root_context.instance.data_dir

    # create session
    session = root_context.create_session()

    # create backup
    try:
        session.backup(backup_name)
    except Exception as e:
        raise ClickException(f"Trilium failed to create backup: {e}")

    backup_filename = f"backup-{backup_name}.db"
    backup_path = data_dir / "backup" / backup_filename if data_dir else None

    if verify:
        assert backup_path

        # validate that trilium created the backup
        if not backup_path.is_file():
            raise ClickException(
                f"Trilium failed to create backup: file '{backup_path}' does not exist"
            )

        mod_time = os.path.getmtime(backup_path)
        mod_datetime = datetime.datetime.fromtimestamp(mod_time)

        delta = (datetime.datetime.now() - mod_datetime).seconds

        if delta > MAX_BACKUP_TIME_DELTA:
            raise ClickException(
                f"Backup '{backup_path}' was written {delta} seconds ago, which is more than the expected maximum of {MAX_BACKUP_TIME_DELTA}"
            )

    logging.info(f"Wrote backup: '{backup_filename}'")

    if dest_path:
        assert backup_path
        # copy backup to destination

        shutil.copyfile(backup_path, dest_path)
        logging.info(f"Copied backup: '{backup_path}' -> '{dest_path}'")


@app.command()
def restore(
    ctx: Context,
    src: Path = Argument(
        help="Source database file", dir_okay=False, exists=True
    ),
):
    """
    Restore database from file
    """

    root_context = get_root_context(ctx, require_data_dir=True)
    data_dir = root_context.instance.data_dir

    assert src.is_file()
    assert data_dir

    dest = data_dir / "document.db"

    # copy backup to database in trilium data dir
    shutil.copyfile(src, dest)

    logging.info(f"Restored backup: '{src}' -> '{dest}'")
