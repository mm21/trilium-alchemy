"""
Utilities specific to CLI functionality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from click import Parameter
from rich.console import Console
from typer import Context, Typer

if TYPE_CHECKING:
    from .main import RootContext

DATETIME_FORMAT = r"%Y-%m-%d %H:%M:%S"
DATETIME_FILE_FORMAT = r"%Y-%m-%d_%H-%M-%S"

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


def get_root_context(ctx: Context) -> RootContext:
    from .main import RootContext

    root_context = ctx.obj
    assert isinstance(root_context, RootContext)
    return root_context


def lookup_param(ctx: Context, name: str) -> Parameter:
    """
    Lookup param by name.
    """
    param = next((p for p in ctx.command.params if p.name == name), None)
    assert param
    return param
