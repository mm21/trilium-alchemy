# TriliumAlchemy

[![Python versions](https://img.shields.io/pypi/pyversions/trilium-alchemy.svg)](https://pypi.org/project/trilium-alchemy)
[![PyPI](https://img.shields.io/pypi/v/trilium-alchemy?color=%2334D058&label=pypi%20package)](https://pypi.org/project/trilium-alchemy)
[![Tests](./badges/tests.svg?dummy=8484744)]()
[![Coverage](./badges/cov.svg?dummy=8484744)]()
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Downloads](https://static.pepy.tech/badge/trilium-alchemy)](https://pepy.tech/project/trilium-alchemy)

Python SDK for [Trilium Notes](https://github.com/zadam/trilium). More features are planned, such as a CLI toolkit with advanced synchronization capability.

## Documentation

Read the full documentation here: <https://mm21.github.io/trilium-alchemy/>

## Getting started

This guide assumes you have some familiarity with Trilium itself; namely the basic concepts of [notes](https://github.com/zadam/trilium/wiki/Note), [attributes](https://github.com/zadam/trilium/wiki/Attributes), and [branches](https://github.com/zadam/trilium/wiki/Tree-concepts).

Install from PyPI:

```bash
pip install trilium-alchemy
```

To connect to a Trilium server, you need to supply either an ETAPI token or password. A token is the recommended mechanism; create a new token in Trilium's UI from Options &rarr; ETAPI. If you provide a password, a temporary token is created for you.

In TriliumAlchemy, the `Session` class is the fundamental interface to interact with Trilium. It implements a [unit of work](https://martinfowler.com/eaaCatalog/unitOfWork.html) pattern, much like [SQLAlchemy's `Session`](https://docs.sqlalchemy.org/en/20/orm/session.html). (In fact, the design for this project was based heavily on SQLAlchemy and therefore inspired its name as well.)

As you make changes to Trilium objects, their state is maintained in the `Session` to which they belong. When you're done making changes and invoke `Session.flush()`, the unit of work dependency solver determines the order in which to commit changes to Trilium and commits them. For example, new notes need to be created before their attributes.

Below is an example of how to create a `Session`:

```python
from trilium_alchemy import Session

# your host here
HOST = "http://localhost:8080"

# your token here
TOKEN = "my-token"

session = Session(HOST, token=TOKEN)
```

Once you're done making changes, simply commit them to Trilium using `Session.flush()`:

```python
session.flush()
```

The `Session` implements a context manager which automatically invokes `flush()` upon exit. For example:

```python
with Session(HOST, token=TOKEN) as session:

    # create a new note under root
    note = Note(title="My note", parents=session.root)

    # session.flush() will be invoked automatically
```

## Working with notes

See the full documentation here: <https://mm21.github.io/trilium-alchemy/sdk/guide/working-with-notes/index.html>

There are 3 kinds of objects in Trilium, represented in TriliumAlchemy as the following classes:

- `Note`
- `BaseAttribute` base class, with concrete classes `Label` and `Relation`
- `Branch`, linking a parent and child note

Once you have a `Session`, you can begin to interact with Trilium. The first `Session` created is registered as the default for any subsequent Trilium objects created.

The following shows an example of creating a new note under today's [day note](https://github.com/zadam/trilium/wiki/Day-notes):

```python
with Session(HOST, token=TOKEN) as session:

    # get today's day note
    today = session.get_today_note()

    # create a new note under today
    note = Note(title="New note about today", parents=today)

    # add some content
    note.content = "<p>Hello, world!</p>"
```

## Pythonic note interfaces

This project implements idiomatic interfaces for working with notes.

### Simple attribute accessor

Values of single-valued attributes can be accessed by indexing into the note itself. For example:

```python
note["myLabel"] = "myValue"
assert note["myLabel"] == "myValue"
```

This creates the label `myLabel` if it doesn't already exist.

The same approach works with relations. For example, to set `~template=Task`:

```python
# assumes you have a template with label #task
task_template = session.search("#template #task")[0]

task = Note(title="My task")
task["template"] = task_template
```

The `~template` relation can be equivalently set during note creation itself:

```python
task = Note(title="My task", template=task_template)
```

### Entity bind operator: `+=`

Use `+=` to add a `Label`, `Relation`, or `Branch`.

Add a label with an optional value:

```python
note += Label("myLabel", "myValue")
assert note.attributes["myLabel"][0].value == "myValue"
```

Add a relation to root note:

```python
note += Relation("myRelation", session.root)
assert note.attributes.owned["myRelation"][0].target is session.root
```

Add a child branch implicitly, with empty branch prefix:

```python
note += Note(title="Child note")
assert note.children[0].title == "Child note"
```

Add a child branch with a branch prefix:

```python
child = Note(title="Child note")

note += Branch(child=child, prefix="My prefix")
assert note.branches.children[0].prefix == "My prefix"
```

Add a parent branch, using the root note as the parent:

```python
note += Branch(parent=session.root, prefix="My prefix")
assert note.branches.parents[0].prefix == "My prefix"
```

Alternatively, pass a `tuple` of (`Note`, `str`) to set the branch prefix:

```python
child = Note(title="Child note")
note += (child, "My prefix")
assert note.branches.children[0].prefix == "My prefix"
```

### Clone operator: `^=`

Use `^=` to add another note as a parent, cloning it:

```python
# get today's day note
today = session.get_today_note()

# clone to today
note ^= today

assert note in today.children
assert today in note.parents
```

Pass a `tuple` of (`Note`, `str`) to set the branch prefix:

```python
note ^= (today, "My prefix")
assert note.branches.parents[0].prefix == "My prefix"
```

## Declarative notes: Notes as code

One of the goals of this project is to enable building, maintaining, and sharing complex note hierarchies using Python. This approach is declarative in nature, inspired by SQLAlchemy's [declarative mapping](https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html#orm-declarative-mapping) approach.

The general idea of declarative programming is that you specify the desired end state, not the steps needed to reach it.

For a fully-featured example of a note hierarchy designed using this approach, see [Event tracker](https://mm21.github.io/trilium-alchemy/sdk/examples/event-tracker.html).

### Note subclasses

The basic technique is to subclass `BaseDeclarativeNote`:

```python
class MyNote(BaseDeclarativeNote):
    title_ = "My note"
```

### Mixin subclasses

Sometimes you want to logically group attributes and/or children together in a reusable way, but don't need a fully-featured `Note`. In those cases you can use a `BaseDeclarativeMixin`.

The basic technique is to subclass {obj}`BaseDeclarativeMixin`:

```python
class MyMixin(BaseDeclarativeMixin): pass
```

`Note` inherits from `BaseDeclarativeMixin`, so the following semantics can be applied to `Note` subclasses and `BaseDeclarativeMixin` subclasses equally.


### Adding labels

Use the decorator `label` to add a label to a `Note` or `BaseDeclarativeMixin` subclass:

```python
@label("sorted")
class SortedMixin(BaseDeclarativeMixin): pass
```

Now you can simply inherit from this mixin if you want a note's children to be sorted:

```python
@label("iconClass", "bx bx-group")
class Contacts(BaseDeclarativeNote, SortedMixin): pass
```

This approach enables reuse of groups of related attributes.

The above is equivalent to the following imperative approach:

```python
contacts = Note(title="Contacts")
contacts += [Label("iconClass", "bx bx-group"), Label("sorted")]
```

### Promoted attributes

A special type of label is one which defines a [promoted attribute](https://github.com/zadam/trilium/wiki/Promoted-attributes). Decorators `label_def` and `relation_def` are provided for convenience.

```python
@label("person")
@label_def("altName", multi=True)
@label_def("birthday", value_type="date")
@relation_def("livesAt")
@relation_def("livedAt", multi=True)
class Person(WorkspaceTemplate):
    icon = "bx bxs-user-circle"
```

## Setting fields

You can set the corresponding fields on `Note` by setting attribute values:

- `title_`
- `note_type_`
- `mime_`
- `content_`

```python
class MyNote(BaseDeclarativeNote):
    title_ = "My title"
    note_type_ = "text"
    mime_ = "text/html"
    content_ = "<p>Hello, world!</p>"
```

## Setting content from file

Set note content from a file by setting `Note.content_file`:

```python
class MyFrontendScript(Note):
    note_type = "code"
    mime = "application/javascript;env=frontend"
    content_file = "assets/myFrontendScript.js"
```

The filename is relative to the package or subpackage the class is defined in. Currently accessing parent paths (`".."`) is not supported.
