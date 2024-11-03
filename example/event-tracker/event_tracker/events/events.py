from trilium_alchemy import (
    BaseFrontendScriptNote,
    BaseSystemNote,
    BaseWorkspaceNote,
    BaseWorkspaceTemplateNote,
    Note,
    Relation,
    children,
    label,
    label_def,
    relation,
    relation_def,
)


@relation_def("person", multi=True)
@relation_def("place")
@label_def("date", value_type="date")
@label("event")
class Event(BaseWorkspaceTemplateNote):
    icon = "bx bx-calendar-event"


@label("birthday")
class Birthday(Event):
    icon = "bx bxs-party"


@label("meeting")
class Meeting(Event):
    icon = "bx bxs-group"


@label("battle")
class Battle(Event):
    icon = "bx bxs-shield-alt-2"


class GetEventsByPerson(BaseFrontendScriptNote):
    content_file = "assets/getEventsByPerson.js"


class GetEventsByPlace(BaseFrontendScriptNote):
    content_file = "assets/getEventsByPlace.js"


class FormatEvents(BaseFrontendScriptNote):
    content_file = "assets/formatEvents.js"


class System(BaseSystemNote):
    workspace_templates = [
        Event,
        Birthday,
        Meeting,
        Battle,
    ]
    scripts = [
        GetEventsByPerson,
        GetEventsByPlace,
        FormatEvents,
    ]


@label("iconClass", "bx bx-calendar")
class Type(Note):
    singleton = True
    leaf = True


class Birthdays(Type):
    pass


class Meetings(Type):
    pass


class Battles(Type):
    pass


@label("iconClass", "bx bxs-calendar-event")
@children(
    Birthdays,
    Meetings,
    Battles,
)
class Events(BaseWorkspaceNote):
    system = System


# common base to provide convenience methods for adding groups of ~person
# relations
class EventInstance(Note):
    # set leaf since this note isn't intended to have declarative children
    # (should be same as if it was created in UI)
    leaf = True

    def add_people(self, *people):
        self.attributes += [Relation("person", person) for person in people]


@relation("template", Birthday)
class BirthdayInstance(EventInstance):
    pass


@relation("template", Meeting)
class MeetingInstance(EventInstance):
    pass


@relation("template", Battle)
class BattleInstance(EventInstance):
    pass
