from __future__ import annotations

from typing import TYPE_CHECKING

from click import MissingParameter, Parameter
from typer import Context, Typer

if TYPE_CHECKING:
    from .main import RootContext


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
