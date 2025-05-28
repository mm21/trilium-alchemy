"""
Filesystem representation of multiple notes in a prefix tree folder format.
"""

from __future__ import annotations

from pathlib import Path

from ..core.note._fs import METADATA_FILENAME
from ..core.note.note import Note

__all__ = [
    "dump_notes",
]


def dump_notes(notes: list[Note], dest_dir: Path, *, prune: bool = False):
    """
    Dump notes to destination folder in prefix tree folder format.
    """

    assert dest_dir.is_dir()

    # collect existing paths to notes, if pruning
    existing_note_paths = _collect_note_paths(dest_dir) if prune else []

    # store paths to dumped notes
    note_paths: list[Note] = []

    # traverse each note
    for note in notes:
        # map note to path
        note_path = dest_dir / _map_note_path(note)

        # dump note to this folder
        note_path.mkdir(parents=True, exist_ok=True)
        note.dump_fs(note_path)

        note_paths.append(note_path)

    if prune:
        # delete existing paths which weren't dumped
        # (presumed deleted in Trilium)

        delete_paths: list[Path] = sorted(
            set(existing_note_paths) - set(note_paths)
        )

        for path in delete_paths:
            path.unlink()


def _map_note_path(note: Note) -> Path:
    """
    Map note to relative path in which it should be placed based on its note_id.
    """
    # TODO


def _collect_note_paths(root: Path) -> list[Path]:
    """
    Collect note paths from root prefix tree folder.
    """

    note_paths: list[Path] = []

    for dirpath, _, filenames in root.walk():
        if METADATA_FILENAME in filenames:
            note_paths.append(dirpath)

    return note_paths
