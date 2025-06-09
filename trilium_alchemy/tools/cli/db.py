from __future__ import annotations

import datetime
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from click import BadParameter, ClickException, MissingParameter
from typer import Argument, Context, Option

from ._utils import (
    MainTyper,
    format_datetime,
    format_file_datetime,
    format_seconds,
    get_root_context,
    logger,
    lookup_param,
)

if TYPE_CHECKING:
    from .main import RootContext

MAX_BACKUP_TIME_DELTA = 10
"""
Maximum number of seconds within which the backup should have been created
by Trilium.
"""

app = MainTyper(
    "db",
    help="Database maintenance operations",
)


@app.callback()
def main(
    ctx: Context,
    data_dir: Path
    | None = Option(
        None,
        help="Directory containing Trilium database, if not specified in config file",
        envvar="TRILIUM_DATA_DIR",
        exists=True,
        file_okay=False,
    ),
):
    root_context = get_root_context(ctx)

    if (
        data_dir
        and "TRILIUM_DATA_DIR" not in os.environ
        and root_context.from_file
    ):
        raise BadParameter(
            message="cannot be passed with config file",
            ctx=ctx,
            param=lookup_param(ctx, "data_dir"),
        )

    # instance-configured data dir takes precedence over parameter
    db_context = DbContext(
        root_context=root_context,
        data_dir=root_context.instance.data_dir or data_dir,
    )

    # replace with new context
    ctx.obj = db_context


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
        False,
        "--verify",
        help=f"Whether to verify by ensuring backup's mtime is < {MAX_BACKUP_TIME_DELTA} seconds ago (requires db --data-dir)",
    ),
    dest: Path
    | None = Option(
        None,
        help="Optional destination database file or folder to copy backup; if folder, filename will use current datetime (requires db --data-dir)",
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

    now = format_file_datetime(datetime.datetime.now())

    # select name
    backup_name = now if auto_name else name

    # normalize destination, if any
    if dest:
        dest_file = dest / f"backup-{now}.db" if dest.is_dir() else dest

        if not dest_file.parent.is_dir():
            raise BadParameter(
                f"destination '{dest}' parent folder does not exist",
                ctx=ctx,
                param=lookup_param(ctx, "dest"),
            )

        # ensure destination path is allowed to be overwritten if it exists
        if dest_file.exists() and not overwrite:
            raise BadParameter(
                f"destination '{dest_file}' exists and --overwrite was not passed",
                ctx=ctx,
                param=lookup_param(ctx, "dest"),
            )
    else:
        dest_file = None

    # determine whether data dir is required
    require_data_dir = bool(dest or verify)

    db_context = _get_db_context(ctx)
    data_dir = db_context.data_dir

    if require_data_dir and not data_dir:
        raise MissingParameter(
            message="required when --dest or --verify is passed",
            ctx=ctx,
            param_hint="db --data-dir",
            param_type="option",
        )

    # create session
    session = db_context.root_context.create_session()

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

        delta = datetime.datetime.now() - mod_datetime

        if delta.seconds > MAX_BACKUP_TIME_DELTA:
            raise ClickException(
                f"Backup '{backup_path}' was written {delta.seconds} seconds ago, which is more than the expected maximum of {MAX_BACKUP_TIME_DELTA}"
            )

        verify_str = f" at {format_datetime(mod_datetime)} ({format_seconds(delta)} seconds ago)"
        backup_str = str(backup_path)
    else:
        verify_str = ""
        backup_str = backup_filename

    logger.info(f"Wrote backup: '{backup_str}'{verify_str}")

    if dest_file:
        assert backup_path

        # copy backup to destination
        shutil.copyfile(backup_path, dest_file)
        logger.info(f"Copied backup: '{backup_path}' -> '{dest_file}'")


@app.command()
def restore(
    ctx: Context,
    src: Path = Argument(
        help="Source database file", dir_okay=False, exists=True
    ),
    dry_run: bool = Option(
        False,
        "--dry-run",
        help="Don't copy, only log source/destination paths",
    ),
    yes: bool = Option(
        False,
        "-y",
        "--yes",
        help="Don't ask for confirmation before overwriting document.db",
    ),
):
    """
    Restore database from file
    """

    db_context = _get_db_context(ctx)
    data_dir = db_context.data_dir

    if not data_dir:
        raise MissingParameter(
            message="required for this command",
            ctx=ctx,
            param=lookup_param(ctx, "data_dir"),
        )

    assert src.is_file()
    dest = data_dir / "document.db"

    copy_str = f"'{src}' -> '{dest}'"

    if dry_run:
        logger.info(f"Would restore backup: {copy_str}")
        return

    if not yes:
        logger.info(f"Will restore backup: {copy_str}")
        if not typer.confirm("Proceed with copy?"):
            return

    # copy backup to database in trilium data dir
    shutil.copyfile(src, dest)

    logger.info(f"Restored backup: {copy_str}")


@dataclass(kw_only=True)
class DbContext:
    root_context: RootContext
    data_dir: Path | None


def _get_db_context(ctx: Context) -> DbContext:
    db_context = ctx.obj
    assert isinstance(db_context, DbContext)
    return db_context
