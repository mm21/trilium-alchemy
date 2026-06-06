"""
Utilities for generic tool-related functionality.
"""
from __future__ import annotations

import typer
from rich.console import Console

from ..core import Note, Session

__all__ = [
    "commit_changes",
    "recurse_notes",
]


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
        session._logger.info("No changes to commit")
        return

    dirty_summary = session.get_dirty_summary()
    overall_summary = session._cache._get_summary()

    session._logger.info("Pending changes:")
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
    session._logger.info("Committed changes")


def recurse_notes(notes: list[Note]) -> list[Note]:
    """
    Recurse into children and aggregate notes.
    """
    aggregated_notes: list[Note] = []
    seen_notes: set[Note] = set()

    for note in notes:
        for n in note.walk():
            if not n in seen_notes:
                seen_notes.add(n)
                aggregated_notes.append(n)

    return aggregated_notes
