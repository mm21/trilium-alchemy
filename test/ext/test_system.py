from trilium_alchemy import *


def test_system(session: Session, note: Note):
    system = BaseRootSystem(note_id=note.note_id, session=session)

    session.flush()

    assert system.children[0].title == "TriliumAlchemySystem"
