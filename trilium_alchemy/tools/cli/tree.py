from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from click import BadParameter, Choice, ClickException, MissingParameter
from typer import Argument, Context, Option

from ...core import BaseDeclarativeNote, Note, Session
from ..utils import commit_changes, recurse_notes
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
    "tree",
    help="Operations on tree or subtree",
)


@app.callback()
def main(
    ctx: Context,
    note_id: str = Option(
        "root",
        help="Note id on which to perform operation",
    ),
    search: str
    | None = Option(
        None,
        help="Search string to identify note on which to perform operation, e.g. '#myProjectRoot'",
    ),
):
    root_context = get_root_context(ctx)
    session = root_context.create_session()

    # get subtree root
    notes = get_notes(
        ctx,
        session,
        note_id=note_id,
        search=search,
        note_id_param=lookup_param(ctx, "note_id"),
        search_param=lookup_param(ctx, "search"),
        exactly_one=True,
    )

    assert len(notes) == 1
    target_note = notes[0]

    tree_context = TreeContext(
        root_context=root_context, session=session, target_note=target_note
    )

    # replace with new context
    ctx.obj = tree_context


@app.command()
def export(
    ctx: Context,
    dest: Path = Argument(
        help="Destination .zip file",
        dir_okay=False,
    ),
    export_format: str = Option(
        "html",
        "--format",
        help="Export format",
        show_choices=True,
        click_type=Choice(["html", "markdown"]),
    ),
    overwrite: bool = Option(
        False,
        "--overwrite",
        help="Whether to overwrite destination file if it already exists",
    ),
):
    """
    Export subtree to .zip file
    """
    if not dest.parent.exists():
        raise BadParameter(
            f"Parent folder of '{dest}' does not exist",
            ctx=ctx,
            param=lookup_param(ctx, "path"),
        )

    if dest.exists() and not overwrite:
        raise MissingParameter(
            f"Destination '{dest}' exists and --overwrite was not passed",
            ctx=ctx,
            param=lookup_param(ctx, "overwrite"),
        )

    tree_context = _get_tree_context(ctx)

    tree_context.target_note.export_zip(
        dest, export_format=export_format, overwrite=overwrite
    )

    logger.info(
        f"Exported note '{tree_context.target_note.title}' (note_id='{tree_context.target_note.note_id}') -> '{dest}'"
    )


@app.command("import")
def import_(
    ctx: Context,
    src: Path = Argument(
        help="Source .zip file",
        dir_okay=False,
        exists=True,
    ),
):
    """
    Import subtree from .zip file
    """
    tree_context = _get_tree_context(ctx)

    # import zip into note
    tree_context.target_note.import_zip(src)


@app.command()
def push(
    ctx: Context,
    note_fqcn: str
    | None = Argument(
        None,
        help="Fully-qualified class name of BaseDeclarativeNote subclass",
    ),
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
    Push declarative note subtree to target note
    """

    tree_context = _get_tree_context(ctx)
    root_note_fqcn = tree_context.root_context.instance.root_note_fqcn
    fqcn = note_fqcn or root_note_fqcn

    if not fqcn:
        raise MissingParameter(
            "must be passed when root_note_fqcn not set in config file",
            ctx=ctx,
            param=lookup_param(ctx, "note_fqcn"),
        )

    if not note_fqcn and root_note_fqcn:
        if not tree_context.target_note.note_id == "root":
            raise ClickException(
                "cannot specify a target note other than root when using root_note_fqcn from config file"
            )

    if not "." in fqcn:
        raise ClickException(
            f"fully-qualified class name '{fqcn}' must contain at least one '.'"
        )

    module_path, obj_name = fqcn.rsplit(".", 1)

    try:
        module = importlib.import_module(module_path)
        note_cls = getattr(module, obj_name)
    except (ImportError, AttributeError) as e:
        raise ClickException(f"failed to import '{fqcn}': {e}")

    if not issubclass(note_cls, BaseDeclarativeNote):
        raise ClickException(
            f"fully-qualified class name '{fqcn}' is not a BaseDeclarativeRoot subclass: {note_cls}"
        )

    # transmute note to have imported subclass, invoking its init
    _ = tree_context.target_note.transmute(note_cls)

    # print summary and commit changes
    commit_changes(tree_context.session, console, dry_run=dry_run, yes=yes)


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

    tree_context = _get_tree_context(ctx)
    notes = recurse_notes([tree_context.target_note])

    for note in notes:
        note._cleanup_positions()

    commit_changes(tree_context.session, console, dry_run=dry_run, yes=yes)


@dataclass(kw_only=True)
class TreeContext:
    root_context: RootContext
    session: Session
    target_note: Note


def _get_tree_context(ctx: Context) -> TreeContext:
    tree_context = ctx.obj
    assert isinstance(tree_context, TreeContext)
    return tree_context
