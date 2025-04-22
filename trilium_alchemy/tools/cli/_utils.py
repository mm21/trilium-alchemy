from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import typer
from click import MissingParameter, Parameter
from rich.console import Console
from typer import Context, Typer

from ...core import Session

if TYPE_CHECKING:
    from .main import RootContext


console = Console()


class MainTyper(Typer):
    """
    Typer app with preconfigured settings.
    """

    def __init__(self, name: str, *, help: str):
        return super().__init__(
            name=name,
            help=help,
            rich_markup_mode="markdown",
            no_args_is_help=True,
            add_completion=False,
        )


def get_root_context(
    ctx: Context, *, require_data_dir: bool = False
) -> RootContext:
    from .main import RootContext

    root_context = ctx.obj
    assert isinstance(root_context, RootContext)

    if require_data_dir:
        data_dir = root_context.instance.data_dir

        if not data_dir:
            raise MissingParameter(
                message="required for this command",
                ctx=root_context.ctx,
                param=lookup_param(root_context.ctx, "data_dir"),
            )

    return root_context


def lookup_param(ctx: Context, name: str) -> Parameter:
    """
    Lookup param by name.
    """
    param = next((p for p in ctx.command.params if p.name == name), None)
    assert param
    return param


def commit_changes(session: Session, *, yes: bool, dry_run: bool):
    """
    Print a summary of changes and handle flags.
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
