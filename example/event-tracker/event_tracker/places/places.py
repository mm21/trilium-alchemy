from trilium_alchemy import (
    Note,
    BaseNoteMixin,
    WorkspaceTemplate,
    Workspace,
    BaseSystem,
    BackendScript,
    Widget,
    label,
    relation,
    label_def,
    relation_def,
    children,
)

from ..events import (
    GetEventsByPlace,
    FormatEvents,
)


# reusable mixin to capture promoted address attributes
@label_def("streetAddress")
@label_def("zip")
class AddressMixin(BaseNoteMixin):
    pass


# reusable mixin to capture promoted coordinate attributes
@label_def("latitude", value_type="number")
@label_def("longitude", value_type="number")
class CoordinateMixin(BaseNoteMixin):
    pass


@label_def("altName", multi=True)
@label("place")
class Place(WorkspaceTemplate):
    leaf = True  # allow user to manage children


@label("residence")
class Residence(Place, AddressMixin):
    icon = "bx bx-building-house"


@label_def("businessName")
class Business(Place, AddressMixin):
    icon = "bx bx-building"


class PointOfInterest(Place, CoordinateMixin):
    icon = "bx bxs-pin"


@label("city")
class City(Place):
    icon = "bx bxs-building"


@label("land")
class Land(Place):
    icon = "bx bxs-map"


class CreateRelation(BackendScript):
    content_file = "assets/createRelation.js"


@children(
    GetEventsByPlace,
    FormatEvents,
)
class RelatedEventsWidget(Widget):
    content_file = "assets/relatedEventsWidget.js"


class ResidentsWidget(Widget):
    content_file = "assets/residentsWidget.js"


class System(BaseSystem):
    workspace_templates = [
        Residence,
        Business,
        PointOfInterest,
        City,
        Land,
    ]
    scripts = [
        CreateRelation,
    ]
    widgets = [
        RelatedEventsWidget,
        ResidentsWidget,
    ]


@label("iconClass", "bx bxs-map-alt")
@label("sorted")
@relation("runOnNoteCreation", CreateRelation, inheritable=True)
@relation("runOnAttributeCreation", CreateRelation, inheritable=True)
class Lands(Note):
    icon = ""
    singleton = True
    leaf = True


@children(
    Lands,
)
class Places(Workspace):
    icon = "bx bxs-map-pin"
    system = System
