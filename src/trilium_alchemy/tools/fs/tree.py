"""
Filesystem operations on a prefix tree of notes.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from logging import Logger
from pathlib import Path

from ...core.exceptions import ValidationError
from ...core.note.content import get_digest
from ...core.note.note import Note
from ...core.session import Session
from ..utils import recurse_notes
from .meta import META_FILENAME, NoteMeta
from .note import dump_note, load_note

__all__ = [
    "dump_tree",
    "load_tree",
    "scan_content",
]

NORM_NOTE_ID_SIZE = 32
"""
Number of characters in normalized note id.

Use 32 characters (128 bits of entropy) since Trilium note ids have
log2(62**12) = 72 bits of entropy.
"""

TREE_DEPTH = 2
"""
Depth of prefix tree. For example:

/dump_root/a1/b2/c3d4...
/dump_root/a1/b3/c4d5...
"""

PREFIX_SIZE = 2
"""
Number of characters in each prefix.
"""

SUFFIX_SIZE = NORM_NOTE_ID_SIZE - TREE_DEPTH * PREFIX_SIZE
"""
Number of characters in note folder.
"""


@dataclass(kw_only=True)
class DumpStats:
    """
    Encapsulates statistics for dump operation.
    """

    note_count: int = 0
    """
    Number of notes dumped to tree.
    """

    update_count: int = 0
    """
    Number of note folders which were actually updated.
    """

    prune_count: int = 0
    """
    Number of note folders which were pruned.
    """


def dump_tree(
    dest_dir: Path,
    notes: list[Note],
    *,
    logger: Logger | None = None,
    recurse: bool = True,
    prune: bool = True,
    check_content_hash: bool = False,
    dry_run: bool = False,
) -> DumpStats:
    """
    Dump notes to destination folder in prefix tree format.
    """

    assert dest_dir.is_dir()

    logger = logger or logging.getLogger()
    dumped_note_dirs: list[Note] = []
    aggregated_notes = recurse_notes(notes) if recurse else notes
    stats = DumpStats(note_count=len(aggregated_notes))

    # traverse each note
    for note in aggregated_notes:
        updated = False

        # map note to folder
        note_dir = dest_dir / _map_note_dir(note)

        # create folder if it doesn't exist
        if not note_dir.exists():
            if dry_run:
                logger.info(f"Would dump {note._str_short} to '{note_dir}'")
                updated = True
            else:
                note_dir.mkdir(parents=True, exist_ok=True)

        if note_dir.exists():
            # dump note to this folder
            updated = dump_note(
                note_dir,
                note,
                logger=logger,
                check_content_hash=check_content_hash,
                dry_run=dry_run,
            )

        dumped_note_dirs.append(note_dir)

        if updated:
            stats.update_count += 1

    # delete existing paths which weren't dumped (presumed deleted in Trilium)
    if prune:
        _prune_dirs(
            dest_dir, dumped_note_dirs, stats, logger=logger, dry_run=dry_run
        )

    return stats


def load_tree(
    src_dir: Path,
    session: Session,
    *,
    logger: Logger | None = None,
    parent_note: Note | None = None,
) -> list[Note]:
    """
    Load notes from source folder and optionally place top-level notes as
    children of parent note.
    """

    logger = logger or logging.getLogger()
    notes: list[Note] = []
    note_dirs = _find_note_dirs(src_dir, logger=logger)

    if not len(note_dirs):
        raise ValidationError(
            [f"Folder does not contain any notes: '{src_dir}'"]
        )

    # load notes
    for note_dir in note_dirs:
        note = load_note(note_dir, session)
        notes.append(note)

    # get top-level notes to ensure they will have a parent
    root_notes = _find_root_notes(notes)

    # if parent given, find relative root notes and add as children
    if parent_note:
        children: set[Note] = set(parent_note.children)

        # validate relative root notes
        invalid_root_notes = {parent_note, session.root}
        errors: list[str] = []

        for note in root_notes:
            if note in invalid_root_notes:
                errors.append(
                    f"Cannot add note {note._str_short} as a child of {parent_note._str_short}, would create a cycle"
                )

        if len(errors):
            raise ValidationError(errors)

        # add children sorted by title, if not already present
        for note in sorted(root_notes, key=lambda n: n.title):
            if note not in children:
                parent_note += note
    else:
        errors: list[str] = []

        for note in root_notes:
            if not len(note.parents):
                errors.append(
                    f"Cannot load note {note._str_short} as it has no parents"
                )

        if len(errors):
            raise ValidationError(errors)

    return notes


def scan_content(
    dump_dir: Path, *, logger: Logger | None = None, dry_run: bool = False
):
    """
    Scan content files and update metadata if out of date. Use if content
    files were updated after dumping.
    """

    logger = logger or logging.getLogger()
    note_dirs = _find_note_dirs(dump_dir, logger=logger)

    for note_dir in note_dirs:
        meta_path = note_dir / META_FILENAME
        content_files = [note_dir / "content.txt", note_dir / "content.bin"]

        content_file = next((f for f in content_files if f.exists()), None)
        assert content_file

        meta = NoteMeta.load_yaml(meta_path)
        current_blob_id = get_digest(content_file.read_bytes())

        if meta.blob_id != current_blob_id:
            title = meta.title.replace("'", "\\'")
            note = f"Note('{title}', note_id='{meta.note_id}')"

            if dry_run:
                logger.info(
                    f"Would update metadata with new blob_id for {note} at '{note_dir}'"
                )
            else:
                meta.blob_id = current_blob_id
                meta.dump_yaml(meta_path)
                logger.info(
                    f"Updated metadata with new blob_id for {note} at '{note_dir}'"
                )


def _find_note_dirs(
    dump_dir: Path, empty_dirs: list[Path] | None = None, *, logger: Logger
) -> list[Path]:
    """
    Walk prefix tree folder and return valid note folders, logging warnings
    for any unexpected files/folders. Optionally populates list of empty
    folders.
    """

    note_dirs: list[Path] = []

    def check_note_dir(dir_path: Path):
        """
        Check if this is a valid note folder and add to note dirs.
        """

        # ensure name is of expected length
        if len(dir_path.name) != SUFFIX_SIZE:
            logger.warning(f"Unexpected folder: '{dir_path}'")
            return

        filenames = {p.name for p in dir_path.iterdir()}

        if META_FILENAME not in filenames:
            logger.warning(
                f"Note folder '{dir_path}' does not contain metadata file"
            )
            return

        filenames.remove(META_FILENAME)

        if len(filenames) != 1 or not (
            filenames < {"content.txt", "content.bin"}
        ):
            logger.warning(
                f"Note folder '{dir_path}' contains ambiguous or missing content file: {filenames}"
            )
            return

        note_dirs.append(dir_path)

    def check_prefix_dir(dir_path: Path) -> bool:
        """
        Check if this folder is a valid prefix folder.
        """

        # ensure name is of expected length
        if len(dir_path.name) != PREFIX_SIZE:
            logger.warning(f"Unexpected folder: '{dir_path}'")
            return False

        # check for empty folder
        if empty_dirs is not None and next(dir_path.iterdir(), None) is None:
            empty_dirs.append(dir_path)

        return True

    def recurse(dir_path: Path, depth: int = 0):
        for path in dir_path.iterdir():
            # ensure not a file
            if path.is_file():
                logger.warning(f"Unexpected file: '{path}'")
                continue

            # ensure dir name is a hex string
            try:
                int(path.name, base=16)
            except ValueError:
                logger.warning(f"Unexpected folder: '{path}'")
                continue

            if depth == TREE_DEPTH:
                check_note_dir(path)
            else:
                if check_prefix_dir(path):
                    recurse(path, depth=depth + 1)

    recurse(dump_dir)

    return note_dirs


def _map_note_dir(note: Note) -> Path:
    """
    Map note to relative path in which it should be placed based on its note_id.

    This is done based on a hash of the note's `note_id`, rather than `note_id`
    itself, primarily to accommodate case-insensitive filesystems.
    """

    # generate hash of note id to get normalized note id
    assert note.note_id
    norm_note_id = _normalize_note_id(note.note_id)

    # generate prefixes
    prefixes = [
        norm_note_id[i * PREFIX_SIZE : (i + 1) * PREFIX_SIZE]
        for i in range(TREE_DEPTH)
    ]

    # trim to get suffix
    suffix = norm_note_id[TREE_DEPTH * PREFIX_SIZE :]

    return "/".join(prefixes + [suffix])


def _prune_dirs(
    dump_dir: Path,
    dumped_note_dirs: list[Path],
    stats: DumpStats,
    *,
    logger: Logger,
    dry_run: bool = False,
):
    """
    Remove existing paths not belonging to dumped notes.
    """

    empty_dirs: list[Path] = []
    note_dirs = _find_note_dirs(dump_dir, empty_dirs, logger=logger)

    # determine which note paths to prune
    stale_note_dirs = sorted(set(note_dirs) - set(dumped_note_dirs))

    # prune stale note paths and empty dirs
    prune_dirs = stale_note_dirs + empty_dirs
    for path in prune_dirs:
        if dry_run:
            logger.info(f"Would prune folder: '{path}'")
        else:
            _prune_dir(dump_dir, path)
        stats.prune_count += 1


def _prune_dir(dump_dir: Path, path: Path):
    """
    Remove this folder and empty parent folders.
    """

    if not path.exists() or dump_dir == path:
        return

    assert path.is_relative_to(dump_dir)
    shutil.rmtree(path)

    # if parent is empty, prune it as well
    parent = path.parent
    if next(parent.iterdir(), None) is None:
        _prune_dir(dump_dir, parent)


def _normalize_note_id(note_id: str) -> str:
    """
    Get fixed-length hex id, well suited for a filesystem prefix tree and
    compatible with case insensitive filesystems.

    Uses SHAKE-128 since we only need 128 bits of entropy; more
    cryptographically optimal than discarding bits from SHA-256 hash.
    """
    return hashlib.shake_128(note_id.encode(encoding="utf-8")).hexdigest(16)


def _find_root_notes(notes: list[Note]) -> list[Note]:
    """
    Traverse notes loaded from filesystem and find ones which are "relative"
    roots, i.e. don't have any parents which are present on the filesystem.
    """

    root_notes: list[Note] = []
    notes_set = set(notes)

    for note in notes:
        if not any(p in notes_set for p in note.parents):
            root_notes.append(note)

    # there must be at least one relative root note or else there is a cycle
    assert len(root_notes)

    return root_notes
