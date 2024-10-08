from trilium_alchemy import *


class Template1(Template):
    pass


class Template2(Template):
    pass


class System1(BaseSystem):
    templates = [Template1]


class System2(System1):
    templates = [Template2]


def test_system(session: Session, note: Note):
    system = BaseRootSystem(note_id=note.note_id, session=session)
    session.flush()

    assert len(system.children) == 7
    assert system.children[0].title == "TriliumAlchemySystem"


def test_system_append(session: Session, note: Note):
    """
    Verify that attributes are appended rather than clobbered.
    """
    system = System2(note_id=note.note_id, session=session)
    session.flush()

    assert len(system.children) == 5
    templates = system.children[0]

    assert templates.title == "Templates"
    assert len(templates.children) == 2
    template2, template1 = templates.children

    assert template1.title == "Template1"
    assert template2.title == "Template2"
