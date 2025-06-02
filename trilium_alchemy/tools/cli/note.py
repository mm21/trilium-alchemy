"""
Operations on one or more notes, not necessarily within the same subtree.

Options to select note(s): (exactly one required)
- --note-id: str | None = None
- --search: str | None = None
- --all: bool = False
    - Apply operation on all notes, or all applicable notes depending on command

Commands:
- sync-template: syncs previously selected notes with this template,
    all notes w/this template if --all; verifies template note has #template
    or #workspaceTemplate
    --template-note-id
    --template-search
    --all-templates
    --dry-run
    -y/--yes
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from typer import Context, Option

from ...core import Session
from ..utils import aggregate_notes, commit_changes
from ._utils import MainTyper, get_notes, get_root_context, lookup_param

if TYPE_CHECKING:
    from .main import RootContext

app = MainTyper(
    "note",
    help="Operations on one or more notes, not necessarily in the same subtree",
)


@app.callback()
def main(
    ctx: Context,
    note_id: str
    | None = Option(
        None,
        "--note-id",
        help="Note id on which to perform operation",
    ),
    search: str
    | None = Option(
        None,
        "--search",
        help="Search string to identify note(s) on which to perform operation, e.g. '#myProjectRoot'",
    ),
    no_recurse: bool = Option(
        False,
        "--no-recurse",
        help="Don't recurse into child notes",
    ),
):
    root_context = get_root_context(ctx)
    session = root_context.create_session()

    note_context = NoteContext(
        root_context=root_context,
        session=session,
        note_id=note_id,
        search=search,
        no_recurse=no_recurse,
    )

    # replace with new context
    ctx.obj = note_context


@app.command()
def cleanup_positions(
    ctx: Context,
    dry_run: bool = Option(
        False,
        "--dry-run",
        help="Only show pending changes",
    ),
    yes: bool = Option(
        False,
        "-y",
        "--yes",
        help="Don't ask for confirmation before committing changes",
    ),
):
    """
    Set attribute and branch positions to intervals of 10, starting with 10
    """
    from .main import console

    note_context = _get_note_context(ctx)

    # get notes
    notes = get_notes(
        ctx.parent,
        note_context.session,
        note_id=note_context.note_id or "root",
        search=note_context.search,
        note_id_param=lookup_param(ctx.parent, "note_id"),
        search_param=lookup_param(ctx.parent, "search"),
    )

    aggregated_notes = (
        aggregate_notes(notes) if not note_context.no_recurse else notes
    )

    for note in aggregated_notes:
        note._cleanup_positions()

    commit_changes(note_context.session, console, dry_run=dry_run, yes=yes)


@dataclass(kw_only=True)
class NoteContext:
    root_context: RootContext
    session: Session
    note_id: str | None
    search: str | None
    no_recurse: bool


def _get_note_context(ctx: Context) -> NoteContext:
    note_context = ctx.obj
    assert isinstance(note_context, NoteContext)
    return note_context
