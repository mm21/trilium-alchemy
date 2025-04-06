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

import logging

import dotenv
from rich.console import Console
from rich.logging import RichHandler

from . import db, tree
from ._utils import MainTyper

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        RichHandler(
            console=Console(),
            rich_tracebacks=True,
            show_level=True,
            show_time=True,
            show_path=False,
        )
    ],
)

dotenv.load_dotenv()

app = MainTyper(
    "trilium-alchemy",
    help="TriliumAlchemy CLI Toolkit",
)
app.add_typer(db.app)
app.add_typer(tree.app)


def run():
    app()


if __name__ == "__main__":
    app()
