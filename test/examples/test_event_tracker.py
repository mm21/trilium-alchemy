"""
Verify the example under examples/event-tracker.
"""
import os
from pathlib import Path

import pexpect

from trilium_alchemy import *


def test_event_tracker(note: Note):
    # add #eventTrackerRoot
    note.labels.append_value("eventTrackerRoot")
    note.flush()

    # use pexpect to handle interactive prompts
    child = pexpect.spawn(
        "python",
        ["-m", "event_tracker"],
        cwd=Path(os.getcwd()) / "examples" / "event-tracker",
    )

    try:
        # confirm declarative notes
        child.expect("Proceed with committing changes?")
        child.sendline("y")

        # confirm example notes
        child.expect("Proceed with committing changes?")
        child.sendline("y")
    except pexpect.exceptions.EOF:
        print(f"Output before: {child.before}")

    _ = child.read()
    child.close()

    assert child.exitstatus == 0
