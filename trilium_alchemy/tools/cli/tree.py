from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from click import BadParameter, Choice, ClickException, MissingParameter
from typer import Argument, Context, Option

from ...core import BaseDeclarativeNote, Note, Session
from ..utils import commit_changes
from ._utils import MainTyper, get_root_context, lookup_param

if TYPE_CHECKING:
    from .main import RootContext


@dataclass(kw_only=True)
class TreeContext:
    root_context: RootContext
    session: Session
    target_note: Note


app = MainTyper(
    "tree",
    help="Operations on tree or subtree",
)


@app.callback()
def main(
    ctx: Context,
    note_id: str = Option(
        "root",
        "--note-id",
        help="Note id on which to perform operation",
    ),
    
    # stub. there is no title search function implemented yet
    # using this param will not yield an error, and will revert to
    # showing root and 1st level children.
    # TODO: implement title search
    title: str
    | None = Option(
        None,
        "--title",
        help="Note title on which to perform operation",
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
        original_search = search
        search = search.strip()
        
        # Initialize results list
        results = []
        
        # Try different search strategies in order of specificity
        search_strategies = [
            # 1. Exact title match (most specific)
            lambda s: session.search(f'note.title = "{s}"'),
            # 2. Label search (if starts with #)
            lambda s: session.search(f'#"{s[1:]}"') if s.startswith('#') else [],
            # 3. Title contains (case-insensitive)
            lambda s: session.search(f'note.title ~= "{s}"'),
            # 4. Content contains (if no results from above)
            lambda s: session.search(f'note.content ~= "{s}"')
        ]
        
        # Try each strategy until we get results
        for strategy in search_strategies:
            if not results:  # Skip if we already have results
                results = strategy(search)
        
        # If we still don't have results, try a more general search
        if not results:
            results = session.search(search)
        
        # Handle the search results
        if not results:
            raise BadParameter(
                f"No notes found matching search: '{original_search}'",
                ctx=ctx,
                param=lookup_param(ctx, "search"),
            )
        elif len(results) > 1:
            error_msg = [
                f"Search '{original_search}' matched {len(results)} notes. Please be more specific.",
                "\nMatching notes (showing first 10):"
            ]
            for i, note in enumerate(results[:10], 1):
                note_type = f" [{note.type}]" if hasattr(note, 'type') else ""
                error_msg.append(f"{i}. {note.title}{note_type} (id: {note.note_id})")
            
            if len(results) > 10:
                error_msg.append(f"... and {len(results) - 10} more")
            
            raise BadParameter(
                "\n".join(error_msg),
                ctx=ctx,
                param=lookup_param(ctx, "search"),
            )
            
        target_note = results[0]
    else:
        target_note = Note(note_id=note_id, session=session)

    tree_context = TreeContext(
        root_context=root_context, session=session, target_note=target_note
    )

    # replace with new context
    ctx.obj = tree_context


@app.command()
def export(
    ctx: Context,
    dest: Path = Argument(
        help="Destination .zip file",
        dir_okay=False,
    ),
    export_format: str = Option(
        "html",
        "--format",
        help="Export format",
        show_choices=True,
        click_type=Choice(["html", "markdown"]),
    ),
    overwrite: bool = Option(
        False,
        "--overwrite",
        help="Whether to overwrite destination file if it already exists",
    ),
):
    """
    Export subtree to .zip file
    """
    if not dest.parent.exists():
        raise BadParameter(
            f"Parent folder of '{dest}' does not exist",
            ctx=ctx,
            param=lookup_param(ctx, "path"),
        )

    if dest.exists() and not overwrite:
        raise MissingParameter(
            f"Destination '{dest}' exists and --overwrite was not passed",
            ctx=ctx,
            param=lookup_param(ctx, "overwrite"),
        )

    tree_context = _get_tree_context(ctx)

    tree_context.target_note.export_zip(
        dest, export_format=export_format, overwrite=overwrite
    )

    logging.info(
        f"Exported note '{tree_context.target_note.title}' (note_id='{tree_context.target_note.note_id}') -> '{dest}'"
    )


@app.command("import")
def import_(
    ctx: Context,
    src: Path = Argument(
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
    tree_context.target_note.import_zip(src)


@app.command("push")
def push(
    ctx: Context,
    note_fqcn: str
    | None = Argument(
        None,
        help="Fully-qualified class name of BaseDeclarativeNote subclass",
    ),
    dry_run: bool = Option(
        False,
        "--dry-run",
        help="Only show pending changes",
    ),
    yes: bool = Option(
        False,
        "-y",
        "--yes",
        help="Don't ask for confirmation before committing changes",
    ),
):
    """
    Push declarative note subtree to target note
    """
    from .main import console

    tree_context = _get_tree_context(ctx)
    root_note_fqcn = tree_context.root_context.instance.root_note_fqcn
    fqcn = note_fqcn or root_note_fqcn

    if not fqcn:
        raise MissingParameter(
            "must be passed when root_note_fqcn not set in config file",
            ctx=ctx,
            param=lookup_param(ctx, "note_fqcn"),
        )

    if not note_fqcn and root_note_fqcn:
        if not tree_context.target_note.note_id == "root":
            raise ClickException(
                "cannot specify a target note other than root when using root_note_fqcn from config file"
            )

    if not "." in fqcn:
        raise ClickException(
            f"fully-qualified class name '{fqcn}' must contain at least one '.'"
        )

    module_path, obj_name = fqcn.rsplit(".", 1)

    try:
        module = importlib.import_module(module_path)
        note_cls = getattr(module, obj_name)
    except (ImportError, AttributeError) as e:
        raise BadParameter(f"failed to import '{fqcn}': {e}")

    if not issubclass(note_cls, BaseDeclarativeNote):
        raise BadParameter(
            f"fully-qualified class name '{fqcn}' is not a BaseDeclarativeRoot subclass: {note_cls} ({type(note_cls)})"
        )

    # transmute note to have imported subclass, invoking its init
    _ = tree_context.target_note.transmute(note_cls)

    # print summary and commit changes
    commit_changes(tree_context.session, console, dry_run=dry_run, yes=yes)


"""
TODO: command: fs-dump [dest: Path]
- option: --propagate-deletes
    - or --no-propagate-deletes, propagate by default
- add Note.walk(): yield subtree recursively
- add Note.fs_dump(dest: Path): dump meta.yaml, content.[txt/bin] to dest folder
    - meta.yaml: title/type/mime, attributes, child branches, blob_id
        - if existing: compare metadata, only update if different
    - content.[txt/bin]: note content, extension based on Note.is_string
- add Session.fs_dump_subtree(dest: Path, note: Note)
    - recursively dumps flattened note subtree to dest folder
    - use Note.walk(), Note.fs_dump() to recurse and dump notes
    - note folder under dest: named as [note_id]
- possible option: --build-hierarchy [dest: Path]
    - recreates note hierarchy in destination using symlinks
        - name folders using branch prefix + note titles, suffix w/note_id 
            if duplicate prefix+title

possible command: fs-load [src: Path]
- could enable bypassing database migration in case of any issue
    - but would not restore settings, only user-visible notes
"""


@app.command("show-hierarchy")
def show_hierarchy(
    ctx: Context,
    debug: bool = Option(
        False,
        "--debug",
        "-d",
        help="Enable debug logging",
    ),
):
    """
    Show the hierarchy from root to the current note in a tree format.
    
    Examples:
        trilium-alchemy tree show-hierarchy --note-id abc123
        trilium-alchemy tree show-hierarchy --search "#myNote"
    """
    # Configure logging
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s: %(message)s" if debug else "%(message)s",
        force=True  # Override any existing handlers
    )
    
    tree_context = _get_tree_context(ctx)
    note = tree_context.target_note

    logging.debug(f"Note: {note}")
    logging.debug(f"Note attributes: {dir(note)}")
    logging.debug(f"Note attributes: {note.__dict__}")
    
    # Get parent and child note IDs
    parent_ids = [parent.note_id for parent in note.parents] if hasattr(note, 'parents') else []
    child_ids = [child.note_id for child in note.children] if hasattr(note, 'children') else []
    
    logging.debug(f"Parent note IDs: {parent_ids}")
    logging.debug(f"Child note IDs: {child_ids}")
    
    # Log note details
    logging.debug(f"Target note: {getattr(note, 'title', 'unknown')} ({getattr(note, 'note_id', 'no-id')})")
    logging.debug(f"Note type: {type(note).__name__}")
    
    # Log session details if available
    session = getattr(note, 'session', None)
    if session:
        logging.debug(f"Session: {session}")
        root_note = getattr(session, 'root_note', None)
        if root_note:
            logging.debug(f"Root note from session: {getattr(root_note, 'title', 'unknown')} ({getattr(root_note, 'note_id', 'no-id')})")
    
    # Build the hierarchy from root to target note
    def get_path_to_root(n):
        path = []
        current = n
        while current is not None:
            path.append(current)
            # Get the first parent (handling the case where there are multiple parents)
            parents = list(getattr(current, 'parents', []))
            current = parents[0] if parents else None
            # Prevent infinite loops in case of cycles
            if current in path:
                break
        return list(reversed(path))
    
    # Get the path from root to the current note
    hierarchy = get_path_to_root(note)
    
    # Log the hierarchy
    logging.debug(f"Found path with {len(hierarchy)} notes from root to target")
    
    # Log the final hierarchy
    if hierarchy:
        logging.debug(f"Hierarchy levels: {len(hierarchy)}")
        for i, h_note in enumerate(hierarchy):
            logging.debug(f"  {i}. {getattr(h_note, 'title', 'unknown')} ({getattr(h_note, 'note_id', 'no-id')}) is_root={getattr(h_note, 'is_root', False)}")
    else:
        logging.debug("No hierarchy found")
    
    # Print the hierarchy
    print("\nHierarchy (from root to target with children):")
    if hierarchy:
        # Print the path from root to target, with target's children
        print_hierarchy(hierarchy, current_note_id=getattr(note, 'note_id', None))


# ============================================================================
# Helper functions
# ============================================================================

def _get_tree_context(ctx: Context) -> TreeContext:
    if not isinstance(ctx.obj, TreeContext):
        raise ClickException("Expected TreeContext")
    return ctx.obj


# ============================================================================
# Hierarchy display
# ============================================================================

def format_note_for_tree(note, is_last: List[bool] = None, is_current: bool = False) -> str:
    """Format a note's name for display in the hierarchy."""
    if is_last is None:
        is_last = []
    
    # Build the tree prefix
    prefix = ""
    for last in is_last[:-1]:
        prefix += "    " if last else "│   "
    if is_last:
        prefix += "└── " if is_last[-1] else "├── "
    
    # Get note properties with defaults
    title = getattr(note, 'title', 'ROOT')
    note_id = getattr(note, 'note_id', 'root')
    
    # Format the note line
    note_line = f"{title} ({note_id})"
    
    # Highlight current note and handle root note
    if note_id == 'root' or getattr(note, 'is_root', False):
        return f"{prefix}🌳 {note_line}"
    if is_current:
        return f"{prefix}👉 {note_line} 👈"
    return f"{prefix}{note_line}"


def print_path_to_note(path: List, current_note_id: str = None, show_children: bool = False) -> None:
    """Print the path from root to target note in a tree format."""
    if not path:
        return
    
    target_note = path[-1]
    
    # Print the root note
    root = path[0]
    print(format_note_for_tree(root, [], is_current=(getattr(root, 'note_id', None) == current_note_id)))
    
    # Print the rest of the path with proper indentation
    prefix = ""
    for i, note in enumerate(path[1:], 1):
        is_last = (i == len(path) - 1)
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}" + format_note_for_tree(note, [], is_current=(getattr(note, 'note_id', None) == current_note_id)).lstrip())
        prefix += "    " if is_last else "│   "
    
    # Print children if this is the target note and show_children is True
    if show_children and getattr(target_note, 'children', None):
        children = list(target_note.children)
        for i, child in enumerate(children):
            is_last_child = (i == len(children) - 1)
            connector = "└── " if is_last_child else "├── "
            print(f"{prefix}{connector}" + format_note_for_tree(child, [], is_current=False).lstrip())


def print_hierarchy(hierarchy: List[tuple], current_note_id: str = None) -> None:
    """Print the path from root to target note in a tree format."""
    if not hierarchy:
        print("No hierarchy found")
        return
    print_path_to_note(hierarchy, current_note_id, show_children=True)
