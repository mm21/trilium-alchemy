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

## Attachments

A note can have any number of attachments, accessed as a list via {obj}`Note.attachments`. Trilium only supports image attachments.

Assign a list of attachments, replacing the existing list, or modify individual items by index or slice. Each item may be an {obj}`Attachment`, a {obj}`pathlib.Path`, or a binary file handle with a `.name`{l=python}:

```python
from pathlib import Path

note.attachments = [
    Attachment(title="image1.png", content=b"..."),
    Path("image2.png"),
    open("image3.png", "rb"),
]

assert len(note.attachments) == 3
```

When a {obj}`pathlib.Path` or file handle is provided, the title and MIME type are derived from the filename. Raw `bytes`{l=python} is not accepted in the list since a title can't be derived; construct an {obj}`Attachment` explicitly with a title instead:

```python
# raises ValueError: no title can be derived
note.attachments = [b"..."]

# ok: title supplied explicitly
note.attachments = [Attachment(title="image.png", content=b"...")]
```

Attachments can also be passed when creating a note:

```python
note = Note(title="My note", attachments=[Path("image.png")])
```

Access an attachment's content as `bytes`{l=python}, along with its {obj}`role <Attachment.role>`, {obj}`mime <Attachment.mime>`, and {obj}`title <Attachment.title>`:

```python
attachment = note.attachments[0]

assert attachment.content == Path("image.png").read_bytes()
assert attachment.role == "image"
```

Save an attachment's content to a file using {obj}`Attachment.save`:

```python
note.attachments[0].save("image_copy.png")
```
