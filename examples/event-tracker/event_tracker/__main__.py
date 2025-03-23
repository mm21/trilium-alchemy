"""
Provides a runner to install example declarative note hierarchy and populate 
it with example notes imperatively.
"""

import argparse
import logging
import os
import sys

import dotenv

from trilium_alchemy import Note, Session

from .setup import setup_declarative, setup_notes

logging.basicConfig(level=logging.INFO)

dotenv.load_dotenv()

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

parser = argparse.ArgumentParser()
parser.add_argument(
    "--clobber",
    action="store_true",
    default=False,
    help="Delete any existing attributes/children of destination note",
)
parser.add_argument(
    "--root", action="store_true", default=False, help="Install to root note"
)

args = parser.parse_args()

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


if args.root:
    # install to root note
    root = Note(note_id="root")
else:
    # lookup destination root
    result = session.search("#eventTrackerRoot")

    if len(result) != 1:
        exit(
            f"Must define exactly one destination note with label #eventTrackerRoot, got {len(result)} (or pass --root to install to root note)"
        )

    root = result[0]

# bail out if existing child notes and user didn't pass --clobber
if len(root.children) != 0 and args.clobber is False:
    exit(
        f"Found existing children of destination note {root.note_id}; pass --clobber to delete"
    )

# ------------------------------------------------------------------------------
# Use declarative approach to generate base note hierarchy. The user can then
# maintain their data under notes designated as "leaf" notes, while leveraging
# a reusable and shareable base hierarchy.
# ------------------------------------------------------------------------------

setup_declarative(session, root)

# ------------------------------------------------------------------------------
# Use imperative approach to generate example data. This mimics notes manually
# added by the user in the UI and also provides an example of how to work with
# notes imperatively.
# ------------------------------------------------------------------------------

setup_notes(session)

# no-op if user provided token
session.logout()
