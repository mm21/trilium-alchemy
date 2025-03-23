from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, override

from click import BadParameter, MissingParameter, Parameter
from trilium_client.exceptions import ApiException
from typer import Context, Exit, Typer
from typer.core import TyperCommand, TyperOption
from typer.models import CommandFunctionType

from ..core import Session

OPERATION_EPILOG = """
    Trilium options can be passed in the following order of precedence:

    * CLI options

    * Environment variables

    * .env file
    """
"""
Epilog to show under operation command options.
"""

OPTION_MSG = "Set via CLI option, environment variable, or .env file."
"""
Message to show upon missing option.
"""


MainOption = partial(TyperOption, show_envvar=True, show_default=True)

HOST_OPTION = MainOption(
    param_decls=["--host"],
    type=str,
    default=None,
    help="Trilium host, e.g. http://localhost:8080",
    envvar="TRILIUM_HOST",
)
TOKEN_OPTION = MainOption(
    param_decls=["--token"],
    type=str,
    default=None,
    help="ETAPI token",
    envvar="TRILIUM_TOKEN",
)
PASSWORD_OPTION = MainOption(
    param_decls=["--password"],
    type=str,
    default=None,
    help="Trilium password",
    envvar="TRILIUM_PASSWORD",
)
DATA_DIR_OPTION = MainOption(
    param_decls=["--trilium_data_dir"],
    type=Path,
    default=None,
    help="Directory containing Trilium database",
    envvar="TRILIUM_DATA_DIR",
)


class MainTyper(Typer):
    """
    Top-level app with preconfigured settings.
    """

    def __init__(self, name: str, *, help: str):
        return super().__init__(
            name=name,
            help=help,
            rich_markup_mode="markdown",
            no_args_is_help=True,
            add_completion=False,
        )


class OperationTyper(MainTyper):
    """
    App which operates on trilium info and optionally data dir.
    """

    def command(
        self, *, require_data_dir: bool = False
    ) -> Callable[[CommandFunctionType], CommandFunctionType]:
        cls = DataOperationCommand if require_data_dir else OperationCommand
        return super().command(cls=cls, epilog=OPERATION_EPILOG)


class OperationCommand(TyperCommand):
    """
    Command which operates on Trilium info.
    """

    @override
    def get_params(self, ctx: Context) -> list[Parameter]:
        return _merge_params(
            super().get_params(ctx),
            [
                HOST_OPTION,
                TOKEN_OPTION,
                PASSWORD_OPTION,
            ],
        )

    @override
    def invoke(self, ctx: Context):
        # extract trilium params into context
        ctx.obj = TriliumOptions(
            host=ctx.params.pop("host", None),
            token=ctx.params.pop("token", None),
            password=ctx.params.pop("password", None),
            trilium_data_dir=ctx.params.pop("trilium_data_dir", None),
        )

        return super().invoke(ctx)


class DataOperationCommand(OperationCommand):
    """
    Command which operates on Trilium info, including data dir.
    """

    @override
    def get_params(self, ctx: Context) -> list[Parameter]:
        return _merge_params(
            super().get_params(ctx),
            [
                DATA_DIR_OPTION,
            ],
        )


@dataclass(kw_only=True)
class TriliumOptions:
    """
    Encapsulates top-level Trilium options from user.
    """

    host: str | None
    token: str | None
    password: str | None
    trilium_data_dir: Path | None


@dataclass(kw_only=True)
class OperationContext:
    """
    Encapsulates top-level Trilium context needed for commands.
    """

    session: Session
    trilium_data_dir: Path | None


def get_operation_context(ctx: Context) -> OperationContext:
    """
    Get trilium context from CLI options and/or environment variables.
    """

    cmd = ctx.command
    assert isinstance(cmd, OperationCommand)

    require_data_dir = isinstance(cmd, DataOperationCommand)

    # get options
    opts = ctx.obj
    assert isinstance(opts, TriliumOptions)

    host = opts.host
    token = opts.token
    password = opts.password
    trilium_data_dir = opts.trilium_data_dir

    # validate args
    if not host:
        raise MissingParameter(message=OPTION_MSG, ctx=ctx, param=HOST_OPTION)
    if not (token or password):
        raise MissingParameter(
            message=OPTION_MSG,
            ctx=ctx,
            param_hint=["token", "password"],
            param_type="option",
        )
    if require_data_dir and not trilium_data_dir:
        raise MissingParameter(
            message=OPTION_MSG,
            ctx=ctx,
            param=DATA_DIR_OPTION,
        )
    if trilium_data_dir and not trilium_data_dir.is_dir():
        raise BadParameter(
            f"Trilium data dir does not exist: {trilium_data_dir}",
            ctx=ctx,
            param=DATA_DIR_OPTION,
        )

    # create a new session
    try:
        session = Session(host, token=token, password=password, default=False)
    except ApiException:
        raise Exit(1)

    return OperationContext(session=session, trilium_data_dir=trilium_data_dir)


def _merge_params(
    super_params: list[Parameter], params: list[Parameter]
) -> list[Parameter]:
    """
    Merge params with superclass, keeping help param at end.
    """
    return super_params[:-1] + params + [super_params[-1]]
