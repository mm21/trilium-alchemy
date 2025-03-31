import logging
from pathlib import Path

from click import BadParameter, Choice, UsageError
from typer import Argument, Context, Option

from ._utils import OperationTyper, get_operation_params, lookup_param

app = OperationTyper(
    "tree",
    help="Tree maintenance operations",
)

# TODO: for export/import: take note spec (note id or label uniquely
# identifying a note)


@app.command(require_session=True, require_note=True)
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
    params = get_operation_params(ctx)
    assert params.session
    assert params.note

    if not path.parent.exists():
        raise BadParameter(
            f"Parent folder of '{path}' does not exist",
            ctx=ctx,
            param=lookup_param(ctx, "path"),
        )

    if path.exists() and not overwrite:
        raise UsageError(
            f"Destination '{path}' exists and --overwrite was not passed",
            ctx=ctx,
        )

    params.note.export_zip(
        path, export_format=export_format, overwrite=overwrite
    )

    logging.info(f"Exported note '{params.note.title}' -> '{path}'")


@app.command("import", require_session=True, require_note=True)
def import_(
    ctx: Context,
    path: Path = Argument(help="Source .zip file"),
):
    """
    Import subtree from .zip file
    """
    params = get_operation_params(ctx)
    assert params.session
    assert params.note

    if not path.is_file():
        raise BadParameter(
            f"Source zip '{path}' does not exist",
            ctx=ctx,
            param=lookup_param(ctx, "path"),
        )

    # import zip into note
    params.note.import_zip(path)
