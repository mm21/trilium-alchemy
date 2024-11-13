"""
Verify the example under example/event-tracker.
"""
import os
import sys

from pytest import mark

from trilium_alchemy import *


@mark.default_session
def test_event_tracker(session: Session, note: Note):
    sys.path.append(f"{os.getcwd()}/example/event-tracker")
    from event_tracker.setup import setup_declarative, setup_notes

    setup_declarative(session, note)
    setup_notes(session)
