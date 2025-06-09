"""
Utilities specific to CLI functionality.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from click import BadParameter, Parameter
from rich.console import Console
from rich.logging import RichHandler
from typer import Context, Typer

from ...core import Note, Session

if TYPE_CHECKING:
    from .main import RootContext


console = Console()

rich_handler = RichHandler(
    console=console,
    rich_tracebacks=True,
    show_level=True,
    show_time=True,
    show_path=False,
)
rich_handler.setFormatter(logging.Formatter("%(message)s"))

logger = logging.getLogger("trilium-alchemy")
logger.setLevel(logging.INFO)
logger.addHandler(rich_handler)
logger.propagate = False


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


def get_root_context(ctx: Context) -> RootContext:
    from .main import RootContext

    root_context = ctx.obj
    assert isinstance(root_context, RootContext)
    return root_context


def get_notes(
    ctx: Context,
    session: Session,
    *,
    note_id: str | None,
    search: str | None,
    note_id_param: Parameter,
    search_param: Parameter,
    exactly_one: bool = False,
) -> list[Note]:
    """
    Get notes from id or search string.
    """
    assert note_id or search

    notes: list[Note]

    if search:
        notes = session.search(search)

        if exactly_one and len(notes) != 1:
            raise BadParameter(
                f"search '{search}' does not uniquely identify a note: got {len(notes)} results",
                ctx=ctx,
                param=search_param,
            )
        elif not len(notes):
            raise BadParameter(
                f"search '{search}' did not return any results",
                ctx=ctx,
                param=search_param,
            )

    else:
        assert note_id

        if not Note._exists(session, note_id):
            raise BadParameter(
                f"note with note_id '{note_id}' does not exist",
                ctx=ctx,
                param=note_id_param,
            )

        notes = [Note(note_id=note_id, session=session)]

    return notes


def lookup_param(ctx: Context, name: str) -> Parameter:
    """
    Lookup param by name.
    """
    param = next((p for p in ctx.command.params if p.name == name), None)
    assert param, f"Could not find param with name: {name}"
    return param


def format_datetime(dt: datetime.datetime) -> str:
    return dt.strftime(r"%Y-%m-%d %H:%M:") + format_seconds(dt)


def format_file_datetime(dt: datetime.datetime) -> str:
    return dt.strftime(r"%Y-%m-%d_%H-%M-") + format_seconds(
        dt, decimal_point="-"
    )


def format_seconds(
    dt: datetime.datetime | datetime.timedelta, decimal_point: str = "."
) -> str:
    seconds, microseconds = (
        (dt.second, dt.microsecond)
        if isinstance(dt, datetime.datetime)
        else (dt.seconds, dt.microseconds)
    )

    return str(round(seconds + microseconds / 1e6, 3)).replace(
        ".", decimal_point
    )
