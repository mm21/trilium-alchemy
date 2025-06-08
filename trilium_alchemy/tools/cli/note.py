"""
Operations on one or more notes, not necessarily within the same subtree.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from click import MissingParameter
from typer import Context, Option

from ...core import Note, Session
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
        help="Note id on which to perform operation",
    ),
    search: str
    | None = Option(
        None,
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
        help="Only log pending changes",
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


@app.command()
def sync_template(
    ctx: Context,
    template_note_id: str
    | None = Option(
        None,
        help="Template note id",
    ),
    template_search: str
    | None = Option(
        None,
        help="Search string to identify template note, e.g. '#template #task'",
    ),
    dry_run: bool = Option(
        False,
        "--dry-run",
        help="Only log pending changes",
    ),
    yes: bool = Option(
        False,
        "-y",
        "--yes",
        help="Don't ask for confirmation before committing changes",
    ),
):
    """
    Sync notes with specified template, or first ~template relation if no template provided; select all notes with given template if no notes provided
    """
    from .main import console

    note_context = _get_note_context(ctx)

    notes: list[Note] | None = None
    template: Note | None = None

    # select template if provided
    if template_note_id or template_search:
        templates = get_notes(
            ctx,
            note_context.session,
            note_id=template_note_id,
            search=template_search,
            note_id_param=lookup_param(ctx, "template_note_id"),
            search_param=lookup_param(ctx, "template_search"),
            exactly_one=True,
        )
        assert len(templates) == 1
        template = templates[0]

        if not (
            "template" in template.labels
            or "workspaceTemplate" in template.labels
        ):
            logging.error(
                f"Template note does not have #template or #workspaceTemplate label: {template._str_short}"
            )
            return

    # select notes if provided
    if note_context.note_id or note_context.search:
        notes = get_notes(
            ctx.parent,
            note_context.session,
            note_id=note_context.note_id,
            search=note_context.search,
            note_id_param=lookup_param(ctx.parent, "note_id"),
            search_param=lookup_param(ctx.parent, "search"),
        )
        assert len(notes)

    # at this point we should have a template and/or selected notes
    if not (notes or template):
        raise MissingParameter(
            message="--note-id/--search and/or --template-note-id/--template-search must be passed",
            ctx=ctx,
            param_hint=[
                "note-id",
                "search",
                "template-note-id",
                "template-search",
            ],
            param_type="option",
        )

    if not notes:
        assert template
        assert template.note_id

        # if we don't have any notes, get all notes with the selected template
        notes = note_context.session.search(f"~template={template.note_id}")

        if not len(notes):
            logging.error(
                f"No notes found with ~template relation to {template._str_short}"
            )
            return

    # now we should have notes, but possibly not a template
    for note in notes:
        # select template
        if template:
            # ensure this note has a ~template relation to this template
            if not template in note.relations.get_targets("template"):
                logging.warning(
                    f"Note {note._str_short} does not have a ~template relation to {template._str_short}"
                )
                continue

            selected_template = template
        else:
            selected_template = note.relations.get_target("template")
            if not selected_template:
                logging.warning(
                    f"Note {note._str_short} does not have a ~template relation"
                )
                continue

        # sync this note with this template
        note.sync_template(selected_template)

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
