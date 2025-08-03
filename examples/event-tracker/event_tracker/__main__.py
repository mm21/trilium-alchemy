"""
Provides a runner to install example declarative note hierarchy and populate 
it with example notes imperatively.
"""

import logging
import os
import sys
from pathlib import Path

import dotenv
from rich.console import Console
from rich.logging import RichHandler

from trilium_alchemy import Session

from .setup import setup_declarative, setup_notes

dotenv.load_dotenv()

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        RichHandler(
            console=console,
            rich_tracebacks=True,
            show_level=True,
            show_time=True,
            show_path=False,
        )
    ],
)

# ensure we have expected environment variables
if not "TRILIUM_HOST" in os.environ:
    sys.exit(
        "TRILIUM_HOST not defined, use .env or set environment variable manually"
    )

if not "TRILIUM_TOKEN" in os.environ and not "TRILIUM_PASSWORD" in os.environ:
    sys.exit(
        "Neither TRILIUM_TOKEN nor TRILIUM_PASSWORD defined, use .env or set environment variable manually for one of these"
    )

host = os.environ.get("TRILIUM_HOST")
token = os.environ.get("TRILIUM_TOKEN", None)
password = os.environ.get("TRILIUM_PASSWORD", None)

session = Session(host, token=token, password=password)


def exit(msg: str):
    """
    Define helper to logout and exit upon error. We could also use a context
    manager (with Session(...) as session) to automatically logout, but prefer
    to reduce indentation.
    Note that logout is only necessary if the user provided a password and not
    a token, otherwise it's a no-op. It's harmless if we used a password and
    forget to logout but it will clutter Trilium with generated tokens.
    """
    session.logout()
    sys.exit(msg)


# ------------------------------------------------------------------------------
# Use declarative approach to generate base note hierarchy. The user can then
# maintain their data under notes designated as "leaf" notes, while leveraging
# a reusable and shareable base hierarchy.
# ------------------------------------------------------------------------------
setup_declarative(Path(__file__).parent.parent)

# ------------------------------------------------------------------------------
# Use imperative approach to generate example data. This mimics notes manually
# added by the user in the UI and also provides an example of how to work with
# notes imperatively.
# ------------------------------------------------------------------------------
setup_notes(session, console)

# no-op if user provided token
session.logout()
