from trilium_alchemy import (
    BaseDeclarativeNote,
    BaseSystemNote,
    BaseWidgetNote,
    BaseWorkspaceNote,
    BaseWorkspaceTemplateNote,
    children,
    label,
    label_def,
    relation_def,
)

from ..events import FormatEvents, GetEventsByPerson


@children(
    GetEventsByPerson,
    FormatEvents,
)
class RelatedEventsWidget(BaseWidgetNote):
    content_file = "assets/relatedEventsWidget.js"


@label("person")
@label_def("altName", multi=True)
@label_def("birthday", value_type="date")
@relation_def("livesAt")
@relation_def("livedAt", multi=True)
class Person(BaseWorkspaceTemplateNote):
    icon = "bx bxs-user-circle"


class Group(BaseWorkspaceTemplateNote):
    icon = "bx bx-group"


class System(BaseSystemNote):
    workspace_templates = [
        Person,
        Group,
    ]
    widgets = [
        RelatedEventsWidget,
    ]


@label("iconClass", "bx bxs-group")
class Groups(BaseDeclarativeNote):
    singleton = True
    leaf = True


@children(
    Groups,
)
class People(BaseWorkspaceNote):
    icon = "bx bxs-user"
    system = System
