from pytest import mark

from trilium_alchemy import *


@mark.default_session
def test_relation(session: Session):
    class Task(BaseTemplateNote):
        icon = "bx bx-task"

    @relation("template", Task)
    class TaskNote(BaseDeclarativeNote):
        pass

    task = TaskNote()

    assert task["template"] is Task()
    assert task["template"]["iconClass"] == "bx bx-task"
