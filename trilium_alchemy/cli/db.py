from pathlib import Path

from typer import Argument, Context, Option

from ._utils import OperationTyper, get_operation_context

app = OperationTyper(
    "db",
    help="Database maintenance operations",
)


@app.command(require_data_dir=True)
def backup(
    ctx: Context,
    path: Path = Argument(
        help="Destination database file or folder; if folder, filename will be generated using current datetime"
    ),
    force: bool = Option(
        False, help="Whether to overwrite destination file if it already exists"
    ),
):
    """
    Backup database to file
    """
    context = get_operation_context(ctx)
    print(f"--- got context: {context}")


@app.command(require_data_dir=True)
def restore(
    ctx: Context,
    path: Path = Argument(help="Source database file"),
):
    """
    Restore database from file
    """
