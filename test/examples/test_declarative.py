from pytest import mark

from trilium_alchemy import *


@mark.default_session
def test_relation(session: Session):
    class Task(BaseTemplateNote):
        icon = "bx bx-task"

    @relation("template", Task)
    class TaskNote(BaseDeclarativeNote):
        pass

    template = Task()
    task = TaskNote()

    assert template is Task()

    session.root += [task, template]
    session.flush()

    task.refresh()

    assert task.relations.get("template").target is template
    assert task.labels.inherited.get_value("iconClass") == "bx bx-task"

    task.delete()
    template.delete()
    session.flush()
