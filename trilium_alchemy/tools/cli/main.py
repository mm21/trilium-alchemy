"""
Entry point of `trilium-alchemy` CLI.

Planned commands:

- `extensions`
    - Manage extensions: List currently installed, install/uninstall/upgrade 
    from path or git repo
        - User-defined destination note for extensions given by 
        `#extensionsRoot` label
- `resync`
    - Re-sync notes with a given template, useful to apply template changes
    to existing notes with that template
- `export`/`import`
    - Export/import (zip file by default)
    - Custom exporter/importer:
        - `export --exporter my_pkg.my_exporter path/to/destination`
- `backup`
    - Create backup in provided path
- `test`
    - Run sanity tests for ETAPI functionality
    - Run stress tests: generate hierarchy with many notes to stress test
    both Trilium itself and TriliumAlchemy
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import dotenv
import typer
from click.exceptions import BadParameter, ClickException, MissingParameter
from pydantic import ValidationError
from rich.logging import RichHandler
from typer import Context, Option

from ...core import Session
from ..config import InstanceConfig, get_config
from . import db, tree
from ._utils import MainTyper, console, get_root_context, lookup_param


@dataclass(kw_only=True)
class RootContext:
    ctx: Context
    instance: InstanceConfig
    from_file: bool

    @classmethod
    def from_config(
        cls,
        *,
        ctx: Context,
        instance_name: str | None = None,
        config_file: Path | None = None,
    ) -> RootContext:
        # ensure config file was passed
        if not config_file:
            raise MissingParameter(
                message="must be passed with --instance",
                ctx=ctx,
                param=lookup_param(ctx, "config_file"),
            )

        # ensure config file exists
        if not config_file.is_file():
            raise BadParameter(
                message=f"file does not exist: {config_file}",
                ctx=ctx,
                param=lookup_param(ctx, "config_file"),
            )

        # get config from file
        try:
            config = get_config(config_file)
        except (ValueError, ValidationError) as e:
            raise BadParameter(
                f"failed to load config file: {e}",
                ctx=ctx,
                param=lookup_param(ctx, "config_file"),
            )

        # get instance from config
        instance = config.instances.get(instance_name)
        if not instance:
            raise BadParameter(
                f"instance '{instance_name}' not found in '{config_file}'",
                ctx=ctx,
                param=lookup_param(ctx, "instance_name"),
            )

        return RootContext(ctx=ctx, instance=instance, from_file=True)

    def create_session(self) -> Session:
        try:
            return self.instance.create_session()
        except Exception as e:
            raise ClickException(f"failed to connect to server: {e}")


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        RichHandler(
            console=console,
            rich_tracebacks=True,
            show_level=True,
            show_time=True,
            show_path=False,
        )
    ],
)

dotenv.load_dotenv()

app = MainTyper(
    "trilium-alchemy",
    help="TriliumAlchemy CLI Toolkit",
)


def _get_host() -> str | None:
    """Get host from environment variable if not provided."""
    return os.environ.get("TRILIUM_HOST")

@app.callback()
def main(
    ctx: Context,
    host: str = Option(
        None,
        "--host",
        help="Trilium host, e.g. http://localhost:8080. Can also be set via TRILIUM_HOST environment variable.",
        envvar="TRILIUM_HOST",
    ),
    token: str
    | None = Option(
        None,
        "--token",
        help="ETAPI token",
        envvar="TRILIUM_TOKEN",
    ),
    password: str
    | None = Option(
        None,
        "--password",
        help="Trilium password",
        envvar="TRILIUM_PASSWORD",
    ),
    instance_name: str
    | None = Option(
        None,
        "--instance",
        help="Instance name as configured in .yaml",
        envvar="TRILIUM_INSTANCE",
    ),
    config_file: Path
    | None = Option(
        "trilium-alchemy.yaml",
        "--config-file",
        help=".yaml file containing instance info, only applicable with --instance",
        envvar="TRILIUM_ALCHEMY_CONFIG_FILE",
        dir_okay=False,
    ),
):
    # Load environment variables from .env file if it exists
    dotenv.load_dotenv(Path('.env').resolve(), override=True)
    
    if instance_name:
        root_context = RootContext.from_config(
            ctx=ctx, instance_name=instance_name, config_file=config_file
        )
    else:
        # Get host from environment if not provided
        if not host:
            host = _get_host()
            if not host:
                raise MissingParameter(
                    message="either --host or --instance must be provided, or set TRILIUM_HOST environment variable",
                    ctx=ctx,
                    param_hint=["host", "instance"],
                    param_type="option",
                )

        # Get token/password from environment if not provided
        token = token or os.environ.get("TRILIUM_TOKEN")
        password = password or os.environ.get("TRILIUM_PASSWORD")
        
        if not (token or password):
            raise MissingParameter(
                message="either --token/TRILIUM_TOKEN or --password/TRILIUM_PASSWORD must be provided",
                ctx=ctx,
                param_hint=["token", "password"],
                param_type="option" if not token and not password else None,
            )

        instance = InstanceConfig(host=host, token=token, password=password)

        root_context = RootContext(
            ctx=ctx,
            instance=instance,
            from_file=False,
        )

    ctx.obj = root_context


app.add_typer(db.app)
app.add_typer(tree.app)


@app.command()
def check(ctx: Context):
    """
    Check Trilium connection
    """
    root_context = get_root_context(ctx)

    try:
        session = root_context.create_session()
    except Exception as e:
        logging.error(f"Failed to connect to Trilium: {e}")
        raise typer.Exit(code=1)
    else:
        logging.info(
            f"Connected to Trilium host '{session.host}', version {session.trilium_version}"
        )


def run():
    app()


if __name__ == "__main__":
    app()
