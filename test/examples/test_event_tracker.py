"""
Verify the example under examples/event-tracker.
"""
import os
import sys

import pexpect

from trilium_alchemy import *


def test_event_tracker(note: Note):
    # add #eventTrackerRoot
    note.labels.append_value("eventTrackerRoot")
    note.flush()

    sys.path.append(f"{os.getcwd()}/examples/event-tracker")

    # use pexpect to handle interactive prompts
    child = pexpect.spawn("python", ["-m", "event_tracker"])

    # confirm declarative notes
    child.expect("Proceed with committing changes?")
    child.sendline("y")

    # confirm example notes
    child.expect("Proceed with committing changes?")
    child.sendline("y")

    _ = child.read()
    child.close()

    assert child.exitstatus == 0
