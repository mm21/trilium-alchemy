from trilium_alchemy import *


class Template1(BaseTemplateNote):
    pass


class Template2(BaseTemplateNote):
    pass


class System1(BaseSystemNote):
    templates = [Template1]


class System2(System1):
    templates = [Template2]


def test_system(session: Session, note: Note):
    system = note.transmute(BaseRootSystemNote)
    session.flush()

    assert len(system.children) == 7
    assert system.children[0].title == "TriliumAlchemySystemNote"


def test_system_append(session: Session, note: Note):
    """
    Verify that attributes are appended rather than clobbered.
    """
    system = note.transmute(System2)
    session.flush()

    assert len(system.children) == 5
    templates = system.children[0]

    assert templates.title == "Templates"
    assert len(templates.children) == 2
    template2, template1 = templates.children

    assert template1.title == "Template1"
    assert template2.title == "Template2"
