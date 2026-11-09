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

    # only built-in system note since no category attributes are set
    assert len(system.children) == 1
    assert system.children[0].title == "TriliumAlchemySystemNote"
    assert [c.title for c in system.children[0].children] == ["Stylesheets"]


def test_system_append(session: Session, note: Note):
    """
    Verify that attributes are appended rather than clobbered.
    """
    system = note.transmute(System2)
    session.flush()

    # empty categories are skipped
    assert len(system.children) == 1
    templates = system.children[0]

    assert templates.title == "Templates"
    assert len(templates.children) == 2
    template2, template1 = templates.children

    assert template1.title == "Template1"
    assert template2.title == "Template2"
