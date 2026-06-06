"""
Operations on one or more notes, not necessarily within the same subtree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from typer import Context, Exit, Option

from ...core import Note, Session
from ..utils import commit_changes
from ._utils import (
    MainTyper,
    console,
    get_notes,
    get_root_context,
    logger,
    lookup_param,
)

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
):
    root_context = get_root_context(ctx)
    session = root_context.create_session()

    note_context = NoteContext(
        root_context=root_context,
        session=session,
        note_id=note_id,
        search=search,
    )

    # replace with new context
    ctx.obj = note_context


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
    Sync notes with specified template, or first ~template relation if no template provided; select all applicable notes if none passed
    """

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
            logger.error(
                f"Template note does not have '#template' or '#workspaceTemplate' label: {template._str_short}"
            )
            raise Exit(1)

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

    # dispatch operation now that inputs have been validated
    _sync_template(note_context.session, notes=notes, template=template)

    commit_changes(note_context.session, console, dry_run=dry_run, yes=yes)


@dataclass(kw_only=True)
class NoteContext:
    root_context: RootContext
    session: Session
    note_id: str | None
    search: str | None


def _get_note_context(ctx: Context) -> NoteContext:
    note_context = ctx.obj
    assert isinstance(note_context, NoteContext)
    return note_context


def _sync_template(
    session: Session,
    *,
    notes: list[Note] | None = None,
    template: Note | None = None,
):
    """
    Invoke template sync operation after validating input.
    """

    notes_norm: list[Note]

    # if no notes passed, look them up from the template (if any)
    if notes is None:
        if template:
            assert template.note_id

            # find all notes with selected template
            notes_norm = session.search(f"~template.noteId={template.note_id}")
        else:
            # find all notes with any template
            notes_norm = session.search("~template")

        # ensure some notes were found
        if not len(notes_norm):
            template_desc = (
                f"~template={template._str_short}"
                if template
                else "any ~template"
            )
            logger.warning(f"No notes found with {template_desc}")
    else:
        notes_norm = notes
        assert len(notes_norm)

    # now we have notes to sync, but possibly not a template
    for note in notes_norm:
        selected_template: Note

        # select template
        if template:
            # ensure this note has a ~template relation to this template
            if not template in note.relations.get_targets("template"):
                logger.warning(
                    f"Note {note._str_short} does not have ~template={template._str_short}"
                )
                continue

            selected_template = template
        else:
            # select first ~template relation
            selected_template = note.relations.get_target("template")
            if not selected_template:
                logger.warning(
                    f"Note {note._str_short} does not have a ~template"
                )
                continue

        # sync this note with this template
        note.sync_template(selected_template)
