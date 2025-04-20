from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from click import BadParameter, Choice, MissingParameter
from typer import Argument, Context, Option

from ...core import BaseDeclarativeNote, Note, Session
from ._utils import MainTyper, get_root_context, lookup_param

if TYPE_CHECKING:
    from .main import RootContext


@dataclass(kw_only=True)
class TreeContext:
    root_context: RootContext
    session: Session
    subtree_root: Note


app = MainTyper(
    "tree",
    help="Tree maintenance operations",
)

# TODO: for export/import: take note spec (note id or label uniquely
# identifying a note)


@app.callback()
def main(
    ctx: Context,
    note_id: str = Option(
        "root",
        "--note-id",
        help="Note id on which to perform operation",
    ),
    search: str
    | None = Option(
        None,
        "--search",
        help="Search string to identify note on which to perform operation, e.g. '#myProjectRoot'",
    ),
):
    root_context = get_root_context(ctx)
    session = root_context.create_session()

    # lookup subtree root
    if search:
        results = session.search(search)
        if len(results) != 1:
            raise BadParameter(
                f"search '{search}' does not uniquely identify a note: got {len(results)} results",
                ctx=ctx,
                param=lookup_param(ctx, "search"),
            )
        subtree_root = results[0]
    else:
        subtree_root = Note(note_id=note_id, session=session)

    context = TreeContext(
        root_context=root_context, session=session, subtree_root=subtree_root
    )

    # replace with new context which encapsulates root context
    ctx.obj = context


@app.command()
def export(
    ctx: Context,
    path: Path = Argument(help="Destination .zip file"),
    export_format: str = Option(
        "html",
        "--format",
        help="Export format",
        show_choices=True,
        click_type=Choice(["html", "markdown"]),
    ),
    overwrite: bool = Option(
        False, help="Whether to overwrite destination file if it already exists"
    ),
):
    """
    Export subtree to .zip file
    """
    if not path.parent.exists():
        raise BadParameter(
            f"Parent folder of '{path}' does not exist",
            ctx=ctx,
            param=lookup_param(ctx, "path"),
        )

    if path.exists() and not overwrite:
        raise MissingParameter(
            f"Destination '{path}' exists and --overwrite was not passed",
            ctx=ctx,
            param=lookup_param(ctx, "overwrite"),
        )

    tree_context = _get_tree_context(ctx)

    tree_context.subtree_root.export_zip(
        path, export_format=export_format, overwrite=overwrite
    )

    logging.info(
        f"Exported note '{tree_context.subtree_root.title}' (note_id='{tree_context.subtree_root.note_id}') -> '{path}'"
    )


@app.command("import")
def import_(
    ctx: Context,
    path: Path = Argument(
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
    tree_context.subtree_root.import_zip(path)


# TODO:
# - if note_fqcn not passed: get FQCN from instance config,
# ensure note_id == root
def push_declarative(
    ctx: Context,
    note_fqcn: str = Option(
        None,
        "--note-fqcn",
        help="Fully-qualified class name of BaseDeclarativeNote subclass",
    ),
):
    if not "." in note_fqcn:
        raise BadParameter(
            f"fully-qualified class name '{note_fqcn}' must contain at least one '.'"
        )

    module_path, obj_name = note_fqcn.rsplit(".", 1)

    try:
        module = importlib.import_module(module_path)
        note_cls = getattr(module, obj_name)
    except (ImportError, AttributeError) as e:
        raise BadParameter(f"failed to import '{note_fqcn}': {e}")

    if not issubclass(note_cls, BaseDeclarativeNote):
        raise BadParameter(
            f"fully-qualified class name '{note_fqcn}' is not a BaseDeclarativeRoot subclass: {note_cls} ({type(note_cls)})"
        )

    tree_context = _get_tree_context(ctx)

    # transmute note to have imported subclass
    tree_context.subtree_root.transmute(note_cls)

    # commit changes
    tree_context.session.flush()


def _get_tree_context(ctx: Context) -> TreeContext:
    tree_context = ctx.obj
    assert isinstance(tree_context, TreeContext)
    return tree_context
