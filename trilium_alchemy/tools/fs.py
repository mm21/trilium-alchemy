"""
Filesystem representation of multiple notes in a prefix tree folder format.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from ..core.note._fs import METADATA_FILENAME
from ..core.note.note import Note
from ..core.session import Session

__all__ = [
    "dump_notes",
    "load_notes",
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


def dump_notes(
    dest_dir: Path,
    notes: list[Note],
    *,
    recursive: bool = True,
    prune: bool = True,
    check_content_hash: bool = False,
):
    """
    Dump notes to destination folder in prefix tree format.
    """

    assert dest_dir.is_dir()

    dumped_note_dirs: list[Note] = []
    aggregated_notes = _aggregate_notes(notes) if recursive else notes

    # traverse each note
    for note in aggregated_notes:
        # map note to folder
        note_dir = dest_dir / _map_note_dir(note)

        # dump note to this folder
        note_dir.mkdir(parents=True, exist_ok=True)
        note.dump_fs(note_dir, check_content_hash=check_content_hash)

        dumped_note_dirs.append(note_dir)

    logging.info(f"Dumped {len(dumped_note_dirs)} notes to '{dest_dir}'")

    # delete existing paths which weren't dumped (presumed deleted in Trilium)
    if prune:
        _prune_dirs(dest_dir, dumped_note_dirs)


def load_notes(
    src_dir: Path,
    session: Session,
    *,
    parent_note: Note | None = None,
) -> list[Note]:
    """
    Load notes from source folder and optionally place top-level notes as
    children of parent note.
    """

    notes: list[Note] = []
    note_dirs = _find_note_dirs(src_dir)

    # load notes
    for note_dir in note_dirs:
        note = Note.load_fs(note_dir, session)
        notes.append(note)

    # if parent given, find relative root notes and add as children
    if parent_note:
        children: set[Note] = set(parent_note.children)
        root_notes = _find_root_notes(notes)

        # validate relative root notes
        invalid_root_notes = {parent_note, session.root}
        for note in root_notes:
            assert (
                note not in invalid_root_notes
            ), f"Cannot add note {note} as a child of {parent_note}"

        # add children sorted by title, if not already present
        for note in sorted(root_notes, key=lambda n: n.title):
            if note not in children:
                parent_note += root_notes

    logging.info(f"Loaded {len(notes)} notes from '{src_dir}'")

    return notes


def _aggregate_notes(notes: list[Note]) -> list[Note]:
    """
    Aggregate notes and children recursively.
    """

    aggregated_notes: set[Note] = set()

    def walk(note: Note):
        aggregated_notes.add(note)
        for child in note.children:
            walk(child)

    for note in notes:
        walk(note)

    return sorted(aggregated_notes, key=lambda n: n.note_id)


def _find_note_dirs(
    root_dir: Path, empty_dirs: list[Path] | None = None
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
            logging.warning(f"Unexpected folder: '{dir_path}'")
            return

        if METADATA_FILENAME in (p.name for p in dir_path.iterdir()):
            note_dirs.append(dir_path)
        else:
            logging.warning(
                f"Note folder '{dir_path}' does not contain metadata file"
            )

    def check_prefix_dir(dir_path: Path) -> bool:
        """
        Check if this folder is a valid prefix folder.
        """

        # ensure name is of expected length
        if len(dir_path.name) != PREFIX_SIZE:
            logging.warning(f"Unexpected folder: '{dir_path}'")
            return False

        # check for empty folder
        if empty_dirs is not None and next(dir_path.iterdir(), None) is None:
            empty_dirs.append(dir_path)

        return True

    def recurse(dir_path: Path, depth: int = 0):
        for path in dir_path.iterdir():
            # ensure not a file
            if path.is_file():
                logging.warning(f"Unexpected file: '{path}'")
                continue

            # ensure dir name is a hex string
            try:
                int(path.name, base=16)
            except ValueError:
                logging.warning(f"Unexpected folder: '{path}'")
                continue

            if depth == TREE_DEPTH:
                check_note_dir(path)
            else:
                if check_prefix_dir(path):
                    recurse(path, depth=depth + 1)

    recurse(root_dir)

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


def _prune_dirs(root_dir: Path, dumped_note_dirs: list[Path]):
    """
    Remove existing paths not belonging to dumped notes.
    """

    empty_dirs: list[Path] = []
    note_dirs = _find_note_dirs(root_dir, empty_dirs)

    # determine which note paths to prune
    stale_note_dirs = sorted(set(note_dirs) - set(dumped_note_dirs))

    # prune stale note paths and empty dirs
    prune_dirs = stale_note_dirs + empty_dirs
    for path in prune_dirs:
        _prune_dir(root_dir, path)

    logging.info(f"Pruned {len(prune_dirs)} note folders")


def _prune_dir(root_dir: Path, path: Path):
    """
    Remove this folder and empty parent folders.
    """

    if not path.exists() or root_dir == path:
        return

    shutil.rmtree(path)

    # if parent is empty, prune it as well
    parent = path.parent
    if next(parent.iterdir(), None) is None:
        _prune_dir(root_dir, parent)


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
