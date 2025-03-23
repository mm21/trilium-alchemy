from pathlib import Path

from click import Choice
from typer import Argument, Option

from ._utils import MainTyper

app = MainTyper(
    "tree",
    help="Tree maintenance operations",
)

# TODO: for export/import: take note spec (note id or label uniquely
# identifying a note)


@app.command()
def export(
    path: Path = Argument(help="Destination .zip file"),
    format: str = Option(
        "html",
        help="Export format",
        show_choices=True,
        click_type=Choice(["html", "markdown"]),
    ),
    force: bool = Option(
        False, help="Whether to overwrite destination file if it already exists"
    ),
):
    """
    Export tree to a .zip file
    """


@app.command(name="import")
def import_(
    path: Path = Argument(help="Source .zip file"),
):
    """
    Import tree from a .zip file
    """
