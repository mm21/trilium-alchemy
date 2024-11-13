"""
Procedures to setup tree with test data.
"""

"""
Provides a runner to install example declarative note hierarchy and populate 
it with example notes imperatively.
"""

import logging

from trilium_alchemy import Label, Note, Relation, Session

from .events import (
    BattleInstance,
    Battles,
    BirthdayInstance,
    Birthdays,
    MeetingInstance,
    Meetings,
)
from .people import Group, Groups, Person
from .places import City, Land, Lands, PointOfInterest, Residence
from .root import Root


def setup_declarative(session: Session, dest_note: Note):
    dest_note.transmute(Root)

    logging.info("Syncing declarative notes")
    session.flush()
    logging.info("Synced declarative notes")


def setup_notes(session: Session):
    # get leaf notes under which to populate test data
    # since these are defined with singleton = True, we'll get the same
    # Note instance every time they're instantiated
    groups = Groups()
    lands = Lands()
    birthdays = Birthdays()
    meetings = Meetings()
    battles = Battles()

    leaf_notes: list[Note] = [
        groups,
        lands,
        birthdays,
        meetings,
        battles,
    ]

    # delete any existing children for all leaf notes
    for note in leaf_notes:
        note.children = []

    # create places using template arg
    shire = Note(title="The Shire", parents=lands, template=Land)
    shire["iconClass"] = "bx bxs-leaf"

    hobbiton = Note(title="Hobbiton", parents=shire, template=City)

    bag_end = Note(title="Bag End", parents=hobbiton, template=Residence)

    eriador = Note(title="Eriador", parents=lands, template=Land)

    rivendell = Note(title="Rivendell", parents=eriador, template=City)
    rivendell += Label("altName", value="Imladris")

    last_homely_house = Note(
        title="The Last Homely House", parents=rivendell, template=Residence
    )

    rohan = Note(title="Rohan", parents=lands, template=Land)

    helms_deep = Note(title="Helm's Deep", parents=rohan, template=City)

    gondor = Note(title="Gondor", parents=lands, template=Land)

    amon_hen = Note(title="Amon Hen", parents=gondor, template=PointOfInterest)

    misty_mountains = Note(
        title="Misty Mountains", parents=lands, template=Land
    )

    moria = Note(title="Moria", parents=misty_mountains, template=City)

    # create rest of notes using Template.instance() helper, effectively same
    # as passing template arg
    bagginses = Group.instance(title="Bagginses", parents=groups)
    fellowship = Group.instance(title="The Fellowship", parents=groups)
    allies = Group.instance(title="Allies of The Fellowship", parents=groups)

    bilbo = Person.instance(title="Bilbo Baggins", parents=bagginses)
    bilbo["birthday"] = "2890-09-22"
    bilbo += Relation("livedAt", bag_end)

    frodo = Person.instance(
        title="Frodo Baggins", parents={bagginses, fellowship}
    )
    frodo["birthday"] = "2968-09-22"
    frodo += Relation("livedAt", bag_end)

    sam = Person.instance(title="Samwise Gamgee", parents=fellowship)
    merry = Person.instance(title="Meriadoc Brandybuck", parents=fellowship)
    pippin = Person.instance(title="Peregrin Took", parents=fellowship)
    gandalf = Person.instance(title="Gandalf", parents=fellowship)
    aragorn = Person.instance(title="Aragorn", parents=fellowship)
    legolas = Person.instance(title="Legolas", parents=fellowship)
    gimli = Person.instance(title="Gimli", parents=fellowship)
    boromir = Person.instance(title="Boromir", parents=fellowship)

    # Gandalf and Aragorn have a lot of names, so add them more concisely

    gandalf_names = [
        "Gandalf the Grey",
        "Gandalf the White",
        "Mithrandir",
        "Olórin",
        "Greyhame",
        "Stormcrow",
    ]
    for name in gandalf_names:
        gandalf += Label("altName", name)

    aragorn_names = [
        "Aragorn II Elessar",
        "Strider",
        "Estel",
        "Thorongil",
        "Elessar Telcontar",
    ]
    for name in aragorn_names:
        aragorn += Label("altName", name)

    elrond = Person.instance(title="Elrond", parents=allies)
    elrond += [
        Label("altName", "Peredhil"),
        Relation("livesAt", last_homely_house),
    ]

    # create events
    bilbo_bday = BirthdayInstance(
        title="Bilbo's eleventy-first birthday", parents=birthdays
    )
    bilbo_bday.add_people(
        bilbo,
        frodo,
        sam,
        merry,
        pippin,
        gandalf,
    )
    bilbo_bday.relations.set_target("place", hobbiton)
    bilbo_bday["date"] = "3001-09-22"
    bilbo_bday.content = "<p>It was a night to remember.</p>"

    formation_fellowship = MeetingInstance(
        title="Formation of the Fellowship", parents=meetings
    )
    formation_fellowship.add_people(
        *fellowship.children,
        elrond,
        bilbo,
    )
    formation_fellowship.relations.set_target("place", last_homely_house)
    formation_fellowship["date"] = "3018-12-18"

    battle_mazarbul = BattleInstance(
        title="Battle in the Chamber of Mazarbul", parents=battles
    )
    battle_mazarbul.add_people(*fellowship.children)
    battle_mazarbul.relations.set_target("place", moria)
    battle_mazarbul["date"] = "3019-01-10"
    battle_mazarbul.content = '<p>"They have a cave troll."</p>'

    breaking_fellowship = MeetingInstance(
        title="Breaking of the Fellowship", parents=meetings
    )
    breaking_fellowship.add_people(
        *[person for person in fellowship.children if person is not gandalf]
    )
    breaking_fellowship.relations.set_target("place", amon_hen)
    breaking_fellowship["date"] = "3019-02-26"

    battle_helms_deep = BattleInstance(
        title="Battle of Helm's Deep", parents=battles
    )
    battle_helms_deep.add_people(
        aragorn,
        legolas,
        gimli,
        gandalf,
    )
    battle_helms_deep.relations.set_target("place", helms_deep)
    battle_helms_deep["date"] = "3019-03-15"

    logging.info("Syncing example notes")
    session.flush()
    logging.info("Synced example notes")
