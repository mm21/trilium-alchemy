(working-with-notes-notes)=
# Notes

## Creation

Create a note by instantiating {obj}`Note`:

```python
note = Note(title="My note")

assert note.title == "My note"
```

Or use a {obj}`Note` subclass to implement custom interfaces, for example attribute accessors:

```python
class MyNote(Note):
    
    @property
    def my_label(self) -> str:
        return self.labels.get_value("myLabel")
    
    @my_label.setter
    def my_label(self, val: str):
        self.labels.set_value("myLabel", val)

note = MyNote(title="My note")

note.my_label = "my_value"
assert note.my_label == "my_value"
```

Every created note must have at least one parent note. You can provide one or more during creation:

```python
note = Note(parents=session.root)
```

The remaining examples assume that you will place the newly created note in your hierarchy by giving it a parent.

## Entity bind operator: `+=`

Use `+=`{l=python} to add a {obj}`Label`, {obj}`Relation`, {obj}`Branch` (parent or child), or child {obj}`Note`.

Add a label:

```python
note += Label("myLabel")
assert note.labels.get_value("myLabel") == ""
```

Add a relation:

```python
note += Relation("myRelation", session.root)
assert note.relations.get_target("myRelation") is session.root
```

Add a child branch implicitly with empty prefix:

```python
note += Note(title="Child note")
assert note.children[0].title == "Child note"
```

Add a child branch implicitly with prefix specified as `tuple[Note, str]`:

```python
note += (Note(title="Child note"), "My prefix")
assert note.children[0].title == "Child note"
```

Or equivalently, explicitly create a {obj}`Branch`:

```python
child = Note(title="Child note")
note += Branch(child=child, prefix="My prefix")

assert note.branches.children[0].prefix == "My prefix"
assert note.children[0] is child
```

Similarly, explicitly create a parent branch:

```python
note += Branch(parent=session.root, prefix="My prefix")
assert note.branches.parents[0].prefix == "My prefix"
```

## Clone operator: `^=`

Use `^=`{l=python} to add another note as a parent, cloning it:

```python
# get today's day note
today = session.get_today_note()

# clone to today
note ^= today
```

Specify a branch prefix by passing a `tuple[Note, str]`:

```python
note ^= (today, "My prefix")
```

## Content

To access note content, get or set {obj}`Note.content`. Content type should be `str`{l=python} if {obj}`Note.is_string` is `True`{l=python}, and `bytes`{l=python} otherwise.

```python
note = Note()
note.content = "<p>Hello, world!</p>"

assert note.content == "<p>Hello, world!</p>"
```

For type-safe access, use {obj}`Note.content_str` or {obj}`Note.content_bin`:

```python
note = Note()
note.content_str = "<p>Hello, world!</p>"

assert note.content_str == "<p>Hello, world!</p>"
```

```{note}
Type-safe accessors will raise {obj}`ValueError` if the content is not of the expected type as determined by {obj}`Note.is_string`.
```
