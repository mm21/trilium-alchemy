from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable, override

from click import BadParameter, MissingParameter, Parameter
from typer import Context, Exit, Typer
from typer.core import TyperCommand, TyperOption
from typer.models import CommandFunctionType

from ...core import Note, Session
from ..config import get_config

YAML_MSG = "Set in .yaml file."
"""
Message to show upon missing field in .yaml config.
"""

OPTION_MSG = "Set via CLI option, environment variable, or .env file."
"""
Message to show upon missing option.
"""


MainOption = partial(TyperOption, show_envvar=True, show_default=True)

# single-instance options
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
    param_decls=["--data-dir"],
    type=Path,
    default=None,
    help="Directory containing Trilium database",
    envvar="TRILIUM_DATA_DIR",
)
DECLARATIVE_ROOT_OPTION = MainOption(
    param_decls=["--declarative-root"],
    type=str,
    default=None,
    help="Fully-qualified class name of declarative note mapped to root note",
    envvar="TRILIUM_ALCHEMY_DECLARATIVE_ROOT",
)

# multi-instance options
INSTANCE_OPTION = MainOption(
    param_decls=["--instance"],
    type=str,
    default=None,
    help="Instance name as configured in .yaml",
)
ALL_INSTANCES_OPTION = MainOption(
    param_decls=["--all-instances"],
    type=bool,
    default=False,
    help="Use all instances from .yaml",
)
CONFIG_FILE_OPTION = MainOption(
    param_decls=["--config-file"],
    type=str,
    default="trilium-alchemy.yaml",
    help=".yaml file containing instance info, only applicable with --instance/--all-instances",
    envvar="TRILIUM_ALCHEMY_CONFIG_FILE",
)

# note-related options
LABEL_OPTION = MainOption(
    param_decls=["--label"],
    type=str,
    default=None,
    help="Select note uniquely identified by label",
)

SINGLE_INSTANCE_OPTIONS = [
    HOST_OPTION,
    TOKEN_OPTION,
    PASSWORD_OPTION,
    DATA_DIR_OPTION,
    DECLARATIVE_ROOT_OPTION,
]

MULTI_INSTANCE_OPTIONS = [
    INSTANCE_OPTION,
    ALL_INSTANCES_OPTION,
    CONFIG_FILE_OPTION,
]

SESSION_OPTIONS = [
    HOST_OPTION,
    TOKEN_OPTION,
    PASSWORD_OPTION,
]


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
        self,
        name: str | None = None,
        *,
        require_session: bool = False,
        require_data_dir: bool = False,
        require_note: bool = False,
        require_declarative_root: bool = False,
    ) -> Callable[[CommandFunctionType], CommandFunctionType]:
        cls = _get_command_cls(
            require_session=require_session,
            require_data_dir=require_data_dir,
            require_target_note=require_note,
            require_declarative_root=require_declarative_root,
        )

        return super().command(name, cls=cls)


class BaseOperationCommand(TyperCommand):
    trilium_require_session: bool
    trilium_require_data_dir: bool
    trilium_require_target_note: bool
    trilium_require_declarative_root: bool

    @override
    def get_params(self, ctx: Context) -> list[Parameter]:
        params: list[Parameter] = []

        if self.trilium_require_session:
            params += SESSION_OPTIONS
        if self.trilium_require_data_dir:
            params.append(DATA_DIR_OPTION)
        if self.trilium_require_target_note:
            params.append(LABEL_OPTION)
        if self.trilium_require_declarative_root:
            params.append(DECLARATIVE_ROOT_OPTION)

        # place multi-instance options at end
        if self.trilium_require_session:
            params += MULTI_INSTANCE_OPTIONS

        return _merge_params(super().get_params(ctx), params)

    @override
    def invoke(self, ctx: Context):
        # get instance context
        if instance := ctx.params.pop("instance", None):
            # get instance from config file
            assert isinstance(instance, str)
            instance_context = _get_instance_from_config(ctx, instance)
            from_yaml = True
        else:
            # get instance from options
            instance_context = _get_instance_from_options(ctx)
            from_yaml = False

        # get note spec context
        note_spec_context = NoteSpecContext(
            label=ctx.params.pop("label", None),
        )

        # extract params into click context
        ctx.obj = OperationContext(
            instance=instance_context,
            note_spec=note_spec_context,
            from_yaml=from_yaml,
        )

        return super().invoke(ctx)


@dataclass(kw_only=True)
class InstanceContext:
    """
    Encapsulates instance-related options.
    """

    host: str | None
    token: str | None
    password: str | None
    data_dir: Path | None
    backup_dir: Path | None = None
    declarative_root: str | None = None


@dataclass(kw_only=True)
class NoteSpecContext:
    """
    Encapsulates options to specify a note.
    """

    label: str | None


@dataclass(kw_only=True)
class OperationContext:
    """
    Encapsulates raw Trilium options from user.
    """

    instance: InstanceContext
    note_spec: NoteSpecContext
    from_yaml: bool


@dataclass(kw_only=True)
class OperationParams:
    """
    Encapsulates top-level Trilium context needed for commands.
    """

    session: Session | None
    data_dir: Path | None
    backup_dir: Path | None
    target_note: Note | None
    declarative_root: str | None


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
    note: Note | None = None

    message = YAML_MSG if operation.from_yaml else OPTION_MSG

    # validate args
    if cmd.trilium_require_session:
        if not operation.instance.host:
            raise MissingParameter(message=message, ctx=ctx, param=HOST_OPTION)
        if not (operation.instance.token or operation.instance.password):
            raise MissingParameter(
                message=message,
                ctx=ctx,
                param_hint=["token", "password"],
                param_type="option",
            )

    if cmd.trilium_require_data_dir:
        if not operation.instance.data_dir:
            raise MissingParameter(
                message=message,
                ctx=ctx,
                param=DATA_DIR_OPTION,
            )
        if not operation.instance.data_dir.is_dir():
            raise BadParameter(
                f"Trilium data dir does not exist: {operation.instance.data_dir}",
                ctx=ctx,
            )

    if cmd.trilium_require_session:
        # create a new session after validating args
        try:
            session = Session(
                operation.instance.host,
                token=operation.instance.token,
                password=operation.instance.password,
                default=False,
            )
        except Exception as e:
            logging.error(f"Failed to create session: {e}")
            raise Exit(1)

    if cmd.trilium_require_target_note:
        assert session

        # lookup note
        if not operation.note_spec.label:
            note = session.root
        else:
            # search for note with label
            results = session.search(f"#{operation.note_spec.label}")
            if len(results) != 1:
                raise BadParameter(
                    f"Label {operation.note_spec.label} does not uniquely identify a note: got {len(results)} results",
                    ctx=ctx,
                    param=LABEL_OPTION,
                )
            note = results[0]

    if cmd.trilium_require_declarative_root:
        if not operation.instance.declarative_root:
            raise MissingParameter(
                message=message,
                ctx=ctx,
                param=DECLARATIVE_ROOT_OPTION,
            )

    return OperationParams(
        session=session,
        data_dir=operation.instance.data_dir,
        backup_dir=operation.instance.backup_dir,
        target_note=note,
        declarative_root=operation.instance.declarative_root,
    )


def lookup_param(ctx: Context, name: str) -> Parameter:
    """
    Lookup param by name.
    """
    param = next((p for p in ctx.command.params if p.name == name), None)
    assert param
    return param


def _get_command_cls(
    *,
    require_session: bool,
    require_data_dir: bool,
    require_target_note: bool,
    require_declarative_root: bool,
) -> type[BaseOperationCommand]:
    """
    Get a command class with required params.
    """

    # define a new class on-the-fly
    # - allows for better scalability than a different class for each
    # combination of params
    class Command(BaseOperationCommand):
        trilium_require_session = require_session
        trilium_require_data_dir = require_data_dir
        trilium_require_target_note = require_target_note
        trilium_require_declarative_root = require_declarative_root

    return Command


def _merge_params(
    super_params: list[Parameter], params: list[Parameter]
) -> list[Parameter]:
    """
    Merge params with superclass, keeping help param at end.
    """
    return super_params[:-1] + params + [super_params[-1]]


def _get_instance_from_config(ctx: Context, instance: str) -> InstanceContext:
    """
    Get instance context from config file with instance.
    """

    # discard single-instance options
    for option in SINGLE_INSTANCE_OPTIONS:
        if option.name in ctx.params:
            del ctx.params[option.name]

    if not "config_file" in ctx.params:
        raise MissingParameter(
            message=OPTION_MSG,
            ctx=ctx,
            param=CONFIG_FILE_OPTION,
        )

    # get config file
    config_file = Path(ctx.params.pop("config_file"))

    if not config_file.is_file():
        raise BadParameter(
            f"Config file does not exist: '{config_file}'",
            ctx=ctx,
            param=CONFIG_FILE_OPTION,
        )

    # get config from file
    config = get_config(config_file)

    all_instances = bool(ctx.params.pop("all_instances", None))

    # TODO: handle multiple instances

    if not instance in config.instances and all_instances:
        raise BadParameter(
            f"Instance '{instance}' not found in '{config_file}'",
            ctx=ctx,
            param=INSTANCE_OPTION,
        )

    data_dir = Path(config.root_data_dir) / instance
    if not data_dir.is_dir():
        raise BadParameter(
            f"Data dir '{data_dir}' from '{config_file}' does not exist",
            ctx=ctx,
            param=CONFIG_FILE_OPTION,
        )

    if path := config.root_backup_dir:
        backup_dir = Path(path) / instance
        if not backup_dir.is_dir():
            raise BadParameter(
                f"Backup dir '{backup_dir}' from '{config_file}' does not exist",
                ctx=ctx,
                param=CONFIG_FILE_OPTION,
            )
    else:
        backup_dir = None

    instance_obj = config.instances[instance]

    return InstanceContext(
        host=instance_obj.host,
        token=instance_obj.token,
        password=instance_obj.password,
        data_dir=data_dir,
        backup_dir=backup_dir,
        declarative_root=instance_obj.declarative_root,
    )


def _get_instance_from_options(ctx: Context) -> InstanceContext:
    """
    Get instance context from options.
    """
    # discard multi-instance options
    for option in MULTI_INSTANCE_OPTIONS:
        if option.name in ctx.params:
            del ctx.params[option.name]

    return InstanceContext(
        host=ctx.params.pop("host", None),
        token=ctx.params.pop("token", None),
        password=ctx.params.pop("password", None),
        data_dir=ctx.params.pop("data_dir", None),
        declarative_root=ctx.params.pop("declarative_root", None),
    )
