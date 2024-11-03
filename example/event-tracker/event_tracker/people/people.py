from trilium_alchemy import (
    BaseSystem,
    Note,
    Widget,
    Workspace,
    WorkspaceTemplate,
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
class RelatedEventsWidget(Widget):
    content_file = "assets/relatedEventsWidget.js"


@label("person")
@label_def("altName", multi=True)
@label_def("birthday", value_type="date")
@relation_def("livesAt")
@relation_def("livedAt", multi=True)
class Person(WorkspaceTemplate):
    icon = "bx bxs-user-circle"


class Group(WorkspaceTemplate):
    icon = "bx bx-group"


class System(BaseSystem):
    workspace_templates = [
        Person,
        Group,
    ]
    widgets = [
        RelatedEventsWidget,
    ]


@label("iconClass", "bx bxs-group")
class Groups(Note):
    singleton = True
    leaf = True


@children(
    Groups,
)
class People(Workspace):
    icon = "bx bxs-user"
    system = System
