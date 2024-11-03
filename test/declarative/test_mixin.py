from pytest import mark
from trilium_alchemy import *


@label("labelm1", "value1")
@label("labelm1-2")
class Mixin1(BaseNoteMixin):
    title = "Mixin1Title"


@label("labelm3")
class Mixin3(BaseNoteMixin):
    pass


@label("labelm2")
class Mixin2(Mixin3):
    title = "Mixin2Title"  # shouldn't get set


@label("label1")
class MixinTest(Note, Mixin1, Mixin2):
    def init(self, attributes, children):
        attributes.append(self.create_declarative_label("label2"))


def test_mixin(session: Session):
    note = MixinTest(session=session)

    assert note.title == "Mixin1Title"

    assert len(note.attributes.owned) == 6
    (
        label1,
        label2,
        labelm1,
        labelm1_2,
        labelm2,
        labelm3,
    ) = note.attributes.owned

    assert label1.name == "label1"
    assert label1.value == ""

    assert label2.name == "label2"
    assert label2.value == ""

    assert labelm1.name == "labelm1"
    assert labelm1.value == "value1"

    assert labelm1_2.name == "labelm1-2"
    assert labelm1_2.value == ""

    assert labelm2.name == "labelm2"
    assert labelm2.value == ""

    assert labelm3.name == "labelm3"
    assert labelm3.value == ""
