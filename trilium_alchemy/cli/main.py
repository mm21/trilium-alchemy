"""
Entry point of `trilium-alchemy` CLI.

Planned commands:

- `extensions`
    - Manage extensions: List currently installed, install/uninstall/upgrade 
    from path or git repo
        - User-defined destination note for extensions given by 
        `#extensionsRoot` label
- `resync`
    - Re-sync notes with a given template, useful to apply template changes
    to existing notes with that template
- `export`/`import`
    - Export/import (zip file by default)
    - Custom exporter/importer:
        - `export --exporter my_pkg.my_exporter path/to/destination`
- `backup`
    - Create backup in provided path
- `test`
    - Run sanity tests for ETAPI functionality
    - Run stress tests: generate hierarchy with many notes to stress test
    both Trilium itself and TriliumAlchemy
"""

from pathlib import Path

from click import Choice
from typer import Argument, Option, Typer

kwargs = dict(
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)

# TODO: for top-level invocation, get connection info in order of priority:
# - CLI args
# - .yaml?
#   - mapping of instance names to connection info
#   - take instance name as arg
# - .env / env vars

app = Typer(
    name="trilium-alchemy",
    help="TriliumAlchemy CLI Toolkit",
    **kwargs,
)

db_app = Typer(
    name="db",
    help="Database maintenance operations",
    **kwargs,
)
app.add_typer(db_app)

tree_app = Typer(
    name="tree",
    help="Tree maintenance operations",
    **kwargs,
)
app.add_typer(tree_app)


# TODO: for backup/restore: ensure trilium data dir set (normally optional)


@db_app.command()
def backup(
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


@db_app.command()
def restore(path: Path = Argument(help="Source database file")):
    """
    Restore database from file
    """


# TODO: for export/import: take note spec (note id or label uniquely
# identifying a note)


@tree_app.command()
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


@tree_app.command(name="import")
def import_(
    path: Path = Argument(help="Source .zip file"),
):
    """
    Import tree from a .zip file
    """


def run():
    app()


if __name__ == "__main__":
    app()
