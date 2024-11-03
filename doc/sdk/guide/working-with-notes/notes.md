(working-with-notes-notes)=
# Notes

## Creation

Create a note by instantiating {obj}`Note`:

```python
note = Note(title="My note")
assert note.title == "My note"
```

Or a {obj}`Note` subclass:

```python
class MyNote(Note):
    title = "My note"

note = MyNote()
assert note.title == "My note"
```

See {ref}`declarative-notes` for more discussion of this concept.

Every created note must have at least one parent note. You can provide one or more during creation:

```python
note = Note(parents=session.root)
```

The remaining examples will assume that you've placed the newly created note in your hierarchy by giving it a parent.

## Entity bind operator: `+=`

Use `+=`{l=python} to add a {obj}`Label`, {obj}`Relation`, or {obj}`Branch` (parent or child).

Add a label:

```python
note += Label("myLabel")
assert note.attributes.owned["myLabel"][0].value == ""
```

Add a relation to root note:

```python
note += Relation("myRelation", session.root)
assert note.attributes.owned["myRelation"][0].target is session.root
```

Add a child branch:

```python
child = Note(title="Child note")
note += Branch(child=child, prefix="My prefix")
assert note.branches.children[0].prefix == "My prefix"
```

Add a parent branch:

```python
note += Branch(parent=session.root, prefix="My prefix")
assert note.branches.parents[0].prefix == "My prefix"
```

Add a child branch implicitly:

```python
note += Note(title="Child note")
assert note.children[0].title == "Child note"
```

Pass a `tuple`{l=python} of ({obj}`Note`, `str`{l=python}) to set the branch prefix:

```python
child = Note(title="Child note")
note += (child, "My prefix")
assert note.branches.children[0].prefix == "My prefix"
```

## Clone operator: `^=`

Use `^=`{l=python} to add another note as a parent, cloning it:

```python
# get today's day note
today = session.get_today_note()

# clone to today
note ^= today
```

Pass a `tuple`{l=python} of ({obj}`Note`, `str`{l=python}) to set the branch prefix:

```python
note ^= (today, "My prefix")
assert note.branches.parents[0].prefix == "My prefix"
```

## Single-valued attributes

Notes can be indexed to get/set a single-valued attribute, or rather the first attribute matching the provided name. 

If no attribute with that name exists, a new one is created. The attribute type ({obj}`Label` or {obj}`Relation`) is inferred by the type of the assigned value.

For example, to set `#priority=10`:

```python
task = Note()
task["priority"] = "10"
assert task["priority"] == "10"
```

To set `~template=Task`:

```python
task_template = session.search("#template #task")[0]

task = Note()
task["template"] = task_template
```

## Multi-valued attributes

To access a list of all attributes of a given name, index into any of the following:

- Combined owned and inherited attributes: {obj}`Note.attributes`
- Owned attributes: `Note.attributes.owned`
- Inherited attributes: `Note.attributes.inherited`

```python
note = Note()

note += [Label("myLabel", "value1"), Label("myLabel", "value2")]

for attr in note.attributes.owned["myLabel"]:
    print(attr)
```
```none
Label(#myLabel, value=value1, attribute_id=None, note=Note(title=new note, note_id=None), position=10)
Label(#myLabel, value=value2, attribute_id=None, note=Note(title=new note, note_id=None), position=20)
```

## Content

To access note content, get or set {obj}`Note.content`. Its type should be `str`{l=python} if {obj}`Note.is_string` is `True`{l=python}, and `bytes`{l=python} otherwise.

```python
note = Note()
note.content = "<p>Hello, world!</p>"
assert note.content == "<p>Hello, world!</p>"
```

It can also be set as an attribute on subclasses:

```python
class MyNote(Note):
    content = "<p>Hello, world!</p>"

note = MyNote()
assert note.content == "<p>Hello, world!</p>"
```

Use {obj}`Note.content_file` or {obj}`BaseNoteMixin.content_file` to set the name of a file relative to this package's location.

```{note}
If you use [Poetry](https://python-poetry.org/) and want to publish a Python note hierarchy with content from a file, no additional steps are needed to package these files if they reside in your project. If you use setuptools, you'll need to use `package_data` or `data_files` to include them (however using setuptools for this is currently untested).
```
