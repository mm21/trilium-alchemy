"""
Filesystem dump/load functionality.

Possible dump option: --build-hierarchy [dest: Path]
- recreates note hierarchy in destination using symlinks
    - name folders using branch prefix + note titles, suffix w/note_id 
    if duplicate prefix+title
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from typer import Argument, Context, Exit, Option

from ...core.exceptions import ValidationError
from ..fs.tree import dump_tree, load_tree, scan_content
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
    pass


app = MainTyper(
    "fs",
    help="Filesystem operations using TriliumAlchemy's note format",
)


@app.command()
def dump(
    ctx: Context,
    dest: Path = Argument(
        help="Destination folder",
        exists=True,
        file_okay=False,
    ),
    note_id: str = Option(
        "root",
        help="Note id to dump",
    ),
    search: str
    | None = Option(
        None,
        help="Search string to identify note(s) to dump, e.g. '#myProjectRoot'",
    ),
    no_recurse: bool = Option(
        False,
        "--no-recurse",
        help="Don't recursively dump child notes",
    ),
    no_prune: bool = Option(
        False,
        "--no-prune",
        help="Don't propagate deleted notes in destination folder",
    ),
    check_content_hash: bool = Option(
        False,
        "--check-content-hash",
        help="Check hash of content file instead of using dump metadata when determining whether content is out of date",
    ),
    dry_run: bool = Option(
        False,
        "--dry-run",
        help="Don't update filesystem, only log operations",
    ),
):
    """
    Dump notes to folder
    """

    root_context = get_root_context(ctx)
    session = root_context.create_session()

    # get source notes
    notes = get_notes(
        ctx,
        session,
        note_id=note_id,
        search=search,
        note_id_param=lookup_param(ctx, "note_id"),
        search_param=lookup_param(ctx, "search"),
    )

    # dump to destination
    stats = dump_tree(
        dest,
        notes,
        recurse=not no_recurse,
        prune=not no_prune,
        check_content_hash=check_content_hash,
        dry_run=dry_run,
    )

    extra = f"{stats.update_count} written, {stats.prune_count} pruned"

    if dry_run:
        logger.info(
            f"Would dump {stats.note_count} notes to '{dest}' ({extra})"
        )
    else:
        logger.info(f"Dumped {stats.note_count} notes to '{dest}' ({extra})")


@app.command()
def load(
    ctx: Context,
    src: Path = Argument(
        help="Source folder",
        exists=True,
        file_okay=False,
    ),
    parent_note_id: str = Option(
        None,
        help="Optional note id of parent under which to place loaded notes",
    ),
    parent_search: str
    | None = Option(
        None,
        help="Optional search string to identify parent under which to place loaded notes, e.g. '#myExtensionsRoot'",
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
    Load notes from dump folder and optionally add as children of given parent
    """

    root_context = get_root_context(ctx)
    session = root_context.create_session()

    # get parent note if requested
    if parent_note_id or parent_search:
        parent_note_results = get_notes(
            ctx,
            session,
            note_id=parent_note_id,
            search=parent_search,
            note_id_param=lookup_param(ctx, "parent_note_id"),
            search_param=lookup_param(ctx, "parent_search"),
            exactly_one=True,
        )
        assert len(parent_note_results) == 1
        parent_note = parent_note_results[0]
    else:
        parent_note = None

    try:
        _ = load_tree(src, session, logger=logger, parent_note=parent_note)
    except ValidationError as e:
        errors = "\n".join(e.errors)
        logger.error(f"Found errors upon loading notes:\n{errors}")
        raise Exit(code=1)

    commit_changes(session, console, dry_run=dry_run, yes=yes)


@app.command()
def scan(
    dump_dir: Path = Argument(
        help="Dump folder as previously passed to dump command",
        exists=True,
        file_okay=False,
    ),
    dry_run: bool = Option(
        False,
        "--dry-run",
        help="Don't update filesystem, only log operations",
    ),
):
    """
    Scan dump folder for content file changes and update metadata if out of date
    """
    scan_content(dump_dir, logger=logger, dry_run=dry_run)
