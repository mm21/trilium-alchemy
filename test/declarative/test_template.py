from trilium_alchemy import *


@label_def("streetAddress")
@label_def("city")
@label_def("state")
@label_def("zip")
class AddressMixin(BaseDeclarativeMixin):
    pass


@label_def("firstName")
@label_def("lastName")
@label_def("phoneNumber")
class ContactTemplate(BaseTemplateNote, AddressMixin):
    icon = "bx bxs-user"


def test_contact(session: Session):
    contact = ContactTemplate(session=session)

    assert "template" in contact.attributes.owned

    # test using class template
    instance1 = Note(template=ContactTemplate, session=session)

    # test using instantiated template
    instance2 = Note(template=contact, session=session)

    assert instance1.relations.get("template").target is contact
    assert instance2.relations.get_target("template") is contact
