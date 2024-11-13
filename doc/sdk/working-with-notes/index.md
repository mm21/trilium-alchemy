# Working with notes

```{toctree}
:hidden:

sessions
notes
attributes
branches
```

This section describes how to work with notes imperatively, i.e. by performing step-by-step note operations.

Following is a brief, self-explanatory example of what will be covered:

```python
with Session(HOST, token=TOKEN) as session:
    
    # lookup task template
    task_template = session.search("#template #task")[0]

    # create a new high priority task
    task = Note(title="Buy cookies", template=task_template)
    task.content = "<p>Chocolate chip</p>"
    task["priority"] = "10"

    # place it under today's day note
    today = session.get_today_note()
    today += task
```
