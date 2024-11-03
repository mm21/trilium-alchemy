from pytest import mark

from trilium_alchemy import *


@mark.default_session
def test_relation(session: Session, note: Note):
    class Task(Template):
        icon = "bx bx-task"

    @relation("template", Task)
    class TaskNote(Note):
        pass

    task = TaskNote()

    assert task["template"] is Task()
    assert task["template"]["iconClass"] == "bx bx-task"
