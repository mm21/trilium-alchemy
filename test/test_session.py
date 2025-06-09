import datetime

from pytest import mark

from trilium_alchemy import *

from .conftest import (
    DATA_DIR,
    HOST,
    PASSWORD,
    TOKEN,
    create_attribute,
    create_note,
)


def test_login_logout():
    session = Session(HOST, password=PASSWORD, default=False)
    session.logout()


def test_context_password():
    with Session(HOST, password=PASSWORD, default=False) as session:
        assert session.api is not None
        assert session._logout_pending is True

        # create a note under root
        root = Note(note_id="root", session=session)
        note = Note(parents={root}, session=session)

        session.flush()

        # cleanup
        note.delete()
        assert note._is_delete

    # session should be logged out
    assert session._logout_pending is False
    assert session._api is None

    # should have flushed note deletion
    assert note._is_clean


def test_context_token():
    with Session(HOST, token=TOKEN, default=False) as session:
        assert session.api is not None
        assert session._logout_pending is False

        # create a note under root
        root = Note(note_id="root", session=session)
        note = Note(parents={root}, session=session)

        assert note._is_create

    # should have flushed note creation
    assert note._is_clean

    # cleanup
    note.delete()

    # session should still be intact
    session.flush()
    assert note._is_clean


def test_get_info(session: Session):
    app_info = session.get_app_info()

    assert app_info is not None
    print(f"Got app_info: {app_info}")


def test_search_label(session: Session, note: Note):
    # give note an attribute to use for searching
    note["testLabel"] = ""
    session.flush()

    # perform search
    results = session.search("#testLabel")
    assert len(results) == 1
    assert results[0] is note

    # manually create a new note and give it a label, using etapi directly
    # to test getting a note in search results which isn't already cached
    note_id = create_note(
        session.api,
        parent_note_id="root",
        content="",
        title="title",
        type="text",
    )

    attr_model = create_attribute(
        session.api,
        type="label",
        note_id=note_id,
        name="testLabel2",
        value="value2",
        is_inheritable=False,
        position=10,
    )
    assert attr_model.attribute_id

    # perform search for new label
    results = session.search("#testLabel2")
    assert len(results) == 1
    assert results[0].note_id == note_id

    results[0].delete()
    session.flush()


def test_search_title(session: Session, note: Note):
    # note already has timestamped title, so it should be unique
    results = session.search(note.title)
    assert len(results) == 1
    assert results[0] is note


def test_backup(session: Session):
    backup_path = DATA_DIR / "backup" / "backup-test.db"

    # remove backup if it exists
    if backup_path.exists():
        backup_path.unlink()

    assert not backup_path.exists()

    # perform backup and ensure it was written
    session.backup("test")
    assert backup_path.exists()


@mark.attribute("label1")
def test_dirty_set(session: Session, note: Note):
    assert session.dirty_count == 0

    # add an entity for create
    note["label2"] = ""
    assert note.attributes[1] in session.dirty_map[State.CREATE]
    assert session.dirty_count == 1
    assert len(session.dirty_map[State.CREATE]) == 1

    # add an entity for update
    note.title = "title2"
    assert note in session.dirty_map[State.UPDATE]
    assert session.dirty_count == 2
    assert len(session.dirty_map[State.UPDATE]) == 1

    # add an entity for delete
    label1 = note.attributes[0]
    label1.delete()
    assert "label1" not in note.attributes

    assert label1 in session.dirty_map[State.DELETE]
    assert session.dirty_count == 3
    assert len(session.dirty_map[State.DELETE]) == 1

    session.flush()
    assert session.dirty_count == 0


def test_calendar(session: Session):
    date = datetime.date(2023, 6, 15)

    session.get_today_note()
    day_note = session.get_day_note(date)
    week_note = session.get_week_note(date)
    month_note = session.get_month_note("2023-06")
    year_note = session.get_year_note("2023-06")
    inbox_note = session.get_inbox_note(date)

    # should have been automatically created
    calendar_root = session.search("#calendarRoot")[0]

    # inbox and day notes should be the same if there's no note with #inbox
    assert inbox_note is day_note

    assert day_note in month_note.children
    assert week_note in month_note.children
    assert month_note in year_note.children
    assert year_note in calendar_root.children

    # just delete calendar root to cleanup
    calendar_root.delete()
    session.flush()


def test_default():
    with Session(HOST, token=TOKEN) as session:
        note = Note(title="My note", parents={session.root})
        assert note._is_create

    assert note._is_clean

    # creating another default session should work as previous was
    # deregistered as default
    session = Session(HOST, token=TOKEN)

    # verify getting entities by id
    # (we need to create a new Note object anyway since the old one is
    # bound to the old session)
    note = Note._from_id(note.note_id)

    label1 = Label("label1")
    note += label1
    label1.flush()
    assert label1.attribute_id is not None
    label1.invalidate()

    label1 = BaseAttribute._from_id(label1.attribute_id)
    assert label1.name == "label1"

    note.delete()
    session.flush()

    session.deregister_default()


def test_refresh_note_ordering(session: Session, note: Note):
    child1 = Note(title="child1", session=session)
    child2 = Note(title="child2", session=session)

    # add children
    note.children = [child1, child2]

    branch1, branch2 = note.branches.children

    assert branch1.position == 10
    assert branch2.position == 20

    # commit position changes to ensure positions are considered changed
    session.flush()

    # swap child positions
    note.branches.children = [branch2, branch1]

    assert branch1.position == 10
    assert branch2.position == 1

    session.flush()
    session.refresh_note_ordering(note)
