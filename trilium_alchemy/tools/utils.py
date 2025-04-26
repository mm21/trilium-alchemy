"""
Utilities for generic tool-related functionality.
"""
from __future__ import annotations

import logging

import typer
from rich.console import Console

from ..core import Session


def commit_changes(
    session: Session,
    console: Console,
    *,
    dry_run: bool = False,
    yes: bool = False,
):
    """
    Print a summary of changes and handle flags.

    ```{todo}
    Add `BaseEntity._rich_str`: returns `rich.text.Text` object with individual
    components styled, e.g. note titles. Avoids need to escape single-quotes
    in titles and model values.
    ```
    """
    if not session._cache.dirty_set:
        logging.info("No changes to commit")
        return

    dirty_summary = session.dirty_summary
    overall_summary = session._cache._get_summary()

    logging.info("Pending changes:")
    console.print(
        f"{dirty_summary}{'\n' if dirty_summary else ''}Summary: {overall_summary}"
    )

    if dry_run:
        return

    if not yes:
        if not typer.confirm("Proceed with committing changes?"):
            return

    # commit changes
    session.flush()

    # print summary
    logging.info("Committed changes")
