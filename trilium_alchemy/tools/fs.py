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

__all__ = [
    "dump_notes",
]

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


def dump_notes(
    notes: list[Note],
    dest_dir: Path,
    *,
    prune: bool = False,
    recursive: bool = False,
):
    """
    Dump notes to destination folder in prefix tree folder format.
    """

    assert dest_dir.is_dir()

    dumped_note_paths: list[Note] = []
    aggregated_notes = _aggregate_notes(notes) if recursive else notes

    # traverse each note
    for note in aggregated_notes:
        # map note to path
        note_path = dest_dir / _map_note_path(note)

        # dump note to this folder
        note_path.mkdir(parents=True, exist_ok=True)
        note.dump_fs(note_path)

        dumped_note_paths.append(note_path)

    # delete existing paths which weren't dumped (presumed deleted in Trilium)
    if prune:
        _prune_paths(dest_dir, dumped_note_paths)


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


def _map_note_path(note: Note) -> Path:
    """
    Map note to relative path in which it should be placed based on its note_id.

    This is done based on a hash of the note's `note_id`, rather than `note_id`
    itself, primarily to accommodate case-insensitive filesystems.
    """

    # generate hash of note's note_id to get "blob id"
    assert note.note_id
    blob_id = hashlib.sha256(note.note_id.encode(encoding="utf-8")).hexdigest()

    print(f"--- blob_id: {blob_id}")

    # generate prefixes
    prefixes = [
        blob_id[i * PREFIX_SIZE : (i + 1) * PREFIX_SIZE + 1]
        for i in range(TREE_DEPTH)
    ]

    # trim blob_id to get suffix
    suffix = blob_id[PREFIX_SIZE * TREE_DEPTH :]

    print(f"--- path: {'/'.join(prefixes + [suffix])}")

    return "/".join(prefixes + [suffix])


def _prune_paths(root: Path, dumped_note_paths: list[Path]):
    """
    Remove existing paths not belonging to dumped notes.
    """

    note_paths: list[Path] = []
    empty_dirs: list[Path] = []

    def check_note_path(dir_path: Path):
        if METADATA_FILENAME in [p.name for p in dir_path.iterdir()]:
            note_paths.append(dir_path)
        else:
            logging.warning(
                f"Note folder '{dir_path}' does not contain metadata file"
            )

    def check_prefix_path(dir_path: Path):
        # ensure folder is a hex value of expected size
        try:
            int(path.name, base=16)
        except ValueError:
            is_hex = False
        else:
            is_hex = True

        if len(path.name) != PREFIX_SIZE or not is_hex:
            logging.warning(f"Unexpected folder: '{path}'")
            return

        # check for empty folder
        if len(dir_path.iterdir()) == 0:
            empty_dirs.append(dir_path)

    def recurse(dir_path: Path, depth: int = 0):
        for path in dir_path.iterdir():
            if path.is_file():
                logging.warning(f"Unexpected file: '{path}'")
                continue

            if depth == TREE_DEPTH:
                check_note_path(path)
            else:
                check_prefix_path(path)
                recurse(path, depth=depth + 1)

    recurse(root)

    # determine which note paths to prune
    stale_note_paths = sorted(set(note_paths) - set(dumped_note_paths))

    # prune stale note paths and empty dirs
    for path in stale_note_paths + empty_dirs:
        _prune_path(path)


def _prune_path(root: Path, path: Path):
    """
    Remove this folder and empty parent folders.
    """

    if not path.exists() or root == path:
        return

    shutil.rmtree(path)

    # if parent is empty, prune it as well
    parent = path.parent
    if not len(parent.iterdir()):
        _prune_path(parent)
