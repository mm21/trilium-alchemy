from __future__ import annotations

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
    App which can operate on trilium session and/or data dir.
    """

    def command(
        self, *, require_session: bool = False, require_data_dir: bool = False
    ) -> Callable[[CommandFunctionType], CommandFunctionType]:
        cls = _get_command_cls(
            require_session=require_session, require_data_dir=require_data_dir
        )
        epilog = (
            OPERATION_EPILOG
            if any([require_session, require_data_dir])
            else None
        )

        return super().command(cls=cls, epilog=epilog)


class BaseOperationCommand(TyperCommand):
    require_trilium_session: bool
    require_trilium_data_dir: bool

    @override
    def get_params(self, ctx: Context) -> list[Parameter]:
        params: list[Parameter] = []

        if self.require_trilium_session:
            params += [
                HOST_OPTION,
                TOKEN_OPTION,
                PASSWORD_OPTION,
            ]
        if self.require_trilium_data_dir:
            params.append(DATA_DIR_OPTION)

        return _merge_params(super().get_params(ctx), params)

    @override
    def invoke(self, ctx: Context):
        # extract trilium params into context
        ctx.obj = OperationContext(
            host=ctx.params.pop("host", None),
            token=ctx.params.pop("token", None),
            password=ctx.params.pop("password", None),
            trilium_data_dir=ctx.params.pop("trilium_data_dir", None),
        )

        return super().invoke(ctx)


@dataclass(kw_only=True)
class OperationContext:
    """
    Encapsulates raw Trilium options from user.
    """

    host: str | None
    token: str | None
    password: str | None
    trilium_data_dir: Path | None


@dataclass(kw_only=True)
class OperationParams:
    """
    Encapsulates top-level Trilium context needed for commands.
    """

    session: Session | None
    trilium_data_dir: Path | None


def get_operation_params(ctx: Context) -> OperationParams:
    """
    Get trilium params from CLI options and/or environment variables.
    """

    # lookup command
    cmd = ctx.command
    assert isinstance(cmd, BaseOperationCommand)

    # lookup operation
    operation = ctx.obj
    assert isinstance(operation, OperationContext)

    session: Session | None = None

    # validate args
    if cmd.require_trilium_session:
        if not operation.host:
            raise MissingParameter(
                message=OPTION_MSG, ctx=ctx, param=HOST_OPTION
            )
        if not (operation.token or operation.password):
            raise MissingParameter(
                message=OPTION_MSG,
                ctx=ctx,
                param_hint=["token", "password"],
                param_type="option",
            )

    if cmd.require_trilium_data_dir:
        if not operation.trilium_data_dir:
            raise MissingParameter(
                message=OPTION_MSG,
                ctx=ctx,
                param=DATA_DIR_OPTION,
            )
        if not operation.trilium_data_dir.is_dir():
            raise BadParameter(
                f"Trilium data dir does not exist: {operation.trilium_data_dir}",
                ctx=ctx,
                param=DATA_DIR_OPTION,
            )

    if cmd.require_trilium_session:
        # create a new session after validating args
        try:
            session = Session(
                operation.host,
                token=operation.token,
                password=operation.password,
                default=False,
            )
        except ApiException:
            raise Exit(1)

    return OperationParams(
        session=session, trilium_data_dir=operation.trilium_data_dir
    )


def _get_command_cls(
    *, require_session: bool, require_data_dir: bool
) -> type[BaseOperationCommand]:
    """
    Get a command class with required params.
    """

    # define a new class on-the-fly
    # - allows for better scalability than a different class for each
    # combination of params
    class Command(BaseOperationCommand):
        require_trilium_session = require_session
        require_trilium_data_dir = require_data_dir

    return Command


def _merge_params(
    super_params: list[Parameter], params: list[Parameter]
) -> list[Parameter]:
    """
    Merge params with superclass, keeping help param at end.
    """
    return super_params[:-1] + params + [super_params[-1]]
