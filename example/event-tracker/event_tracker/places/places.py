from trilium_alchemy import (
    BaseBackendScriptNote,
    BaseDeclarativeMixin,
    BaseSystemNote,
    BaseWidgetNote,
    BaseWorkspaceNote,
    BaseWorkspaceTemplateNote,
    Note,
    children,
    label,
    label_def,
    relation,
)

from ..events import FormatEvents, GetEventsByPlace


# reusable mixin to capture promoted address attributes
@label_def("streetAddress")
@label_def("zip")
class AddressMixin(BaseDeclarativeMixin):
    pass


# reusable mixin to capture promoted coordinate attributes
@label_def("latitude", value_type="number")
@label_def("longitude", value_type="number")
class CoordinateMixin(BaseDeclarativeMixin):
    pass


@label_def("altName", multi=True)
@label("place")
class Place(BaseWorkspaceTemplateNote):
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


class CreateRelation(BaseBackendScriptNote):
    content_file = "assets/createRelation.js"


@children(
    GetEventsByPlace,
    FormatEvents,
)
class RelatedEventsWidget(BaseWidgetNote):
    content_file = "assets/relatedEventsWidget.js"


class ResidentsWidget(BaseWidgetNote):
    content_file = "assets/residentsWidget.js"


class System(BaseSystemNote):
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
class Places(BaseWorkspaceNote):
    icon = "bx bxs-map-pin"
    system = System
