from pathlib import Path

from typer import Argument, Context, Option

from ._utils import TriliumDataTyper, get_trilium_context

app = TriliumDataTyper(
    "db",
    help="Database maintenance operations",
)


@app.command()
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

    trilium_context = get_trilium_context(ctx, data_dir_required=True)

    print(f"--- got trilium_context: {trilium_context}")


@app.command()
def restore(path: Path = Argument(help="Source database file")):
    """
    Restore database from file
    """
