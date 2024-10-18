(declarative-notes)=
# Declarative notes: Notes as code

One of the goals of this project is to enable building, maintaining, and sharing complex note hierarchies using Python. This approach is declarative in nature, inspired by SQLAlchemy's [declarative mapping](https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html#orm-declarative-mapping) approach.

The general idea of declarative programming is that you specify the desired end state, not the steps needed to reach it.

For a fully-featured example of a note hierarchy designed using this approach, see {ref}`event-tracker`.

## Note subclasses

The basic technique is to subclass {obj}`Note`:

```python
class MyNote(Note): pass
```

## Mixin subclasses

Sometimes you want to logically group attributes or children together in a reusable way, but don't need a fully-featured {obj}`Note`. In those cases you can use a {obj}`Mixin`.

The basic technique is to subclass {obj}`Mixin`:

```python
class MyMixin(Mixin): pass
```

```{note}
{obj}`Note` inherits from {obj}`Mixin`, so the following semantics can be applied to {obj}`Note` subclasses and {obj}`Mixin` subclasses equally.
```

## Setting fields

You can set the following fields by setting attribute values:

- {obj}`Note.title` or {obj}`Mixin.title`
- {obj}`Note.note_type` or {obj}`Mixin.note_type`
- {obj}`Note.mime` or {obj}`Mixin.mime`
- {obj}`Note.content`

```python
class MyNote(Note):
    title = "My title"
    note_type = "text"
    mime = "text/html"
    content = "<p>Hello, world!</p>"
```

## Setting content from file

Set note content from a file by setting {obj}`Note.content_file` or {obj}`Mixin.content_file`:

```python
class MyFrontendScript(Note):
    note_type = "code"
    mime = "application/javascript;env=frontend"
    content_file = "assets/myFrontendScript.js"
```

The filename is relative to the package the class is defined in. Currently accessing parent paths (`".."`{l=python}) is not supported.

## Adding labels

Use the decorator {obj}`label` to add a label:

```python
@label("sorted")
class Sorted(Mixin): pass
```

Now you can simply subclass this mixin if you want a note's children to be sorted:

```python
@label("iconClass", "bx bx-group")
class Contacts(Note, Sorted): pass
```

The above is equivalent to the following imperative approach:

```python
contacts = Note(title="Contacts")
contacts += [Label("iconClass", "bx bx-group"), Label("sorted")]
```

### Promoted attributes

A special type of label is one which defines a [promoted attribute](https://github.com/zadam/trilium/wiki/Promoted-attributes). Decorators {obj}`label_def` and {obj}`relation_def` are provided for convenience.

```python
@label("person")
@label_def("altName", multi=True)
@label_def("birthday", value_type="date")
@relation_def("livesAt")
@relation_def("livedAt", multi=True)
class Person(WorkspaceTemplate):
    icon = "bx bxs-user-circle"
```

## Singleton notes

In some cases it's important to generate the same {obj}`Note.note_id` every time the class is instantiated. Templates, for example, should have only one instance and be automatically updated as changes are made to the code. This behavior can be accomplished in a number of ways.

```{warning}
Without setting {obj}`Note.leaf` or {obj}`Mixin.leaf`, TriliumAlchemy assumes that you want to explicitly specify the note's children. Therefore it will delete any existing children which aren't declaratively added. See {ref}`leaf-notes` to learn more.
```

### Setting `singleton`

When {obj}`Note.singleton` or {obj}`Mixin.singleton` is set, the note's {obj}`Note.note_id` is generated based on the fully qualified class name, i.e. the class name including its modpath.

The following creates a template note for a task:

```python
@label("template")
@label("iconClass", "bx bx-task")
class Task(Note):
    singleton = True
```

### Setting `note_id_seed`

When {obj}`Note.note_id_seed` or {obj}`Mixin.note_id_seed` is set, the provided value is hashed to generate {obj}`Note.note_id`.

It uses the same hash algorithm used by {obj}`Mixin.singleton`.

```python
# now note_id won't change if we move the class to a different module
@label("template")
@label("iconClass", "bx bx-task")
class Task(Note):
    note_id_seed = "Task"
```

```{todo}
Add a flag to set {obj}`Mixin.note_id_seed` from class name (user guarantees uniqueness of class names)
```

### Setting `note_id`

When {obj}`Note.note_id` or {obj}`Mixin.note_id` is set, the provided value is used as {obj}`Note.note_id` directly.

```python
class MyNote(Note):
    note_id = "my_note_id"
```

### Passing `note_id`

When `note_id` is passed in the constructor of a {obj}`Note` subclass, it's similarly considered a singleton.

### Child of singleton

Every child of a singleton note is required to also have a deterministic {obj}`Note.note_id`. Therefore a `note_id` is generated for children of singletons, even if they don't satisfy any of the above criteria. 

This is recursive, so an entire note tree specified by {obj}`Note` subclasses will be instantiated with a deterministic `note_id` if the root satisfies any of the above criteria.

## Adding relations

You can declaratively add a relation to another note, as long as the target note is a singleton.

For example, to create a `~template` relation:

```python
@relation("template", Task)
class TaskInstance(Note): pass
```

Now you can create a task by simply instantiating `TaskInstance`, and it will automatically have `~template=Task`.

## Adding children

Use {obj}`children` or {obj}`child` to add children:

```python
class Child1(Note): pass
class Child2(Note): pass
class Child3(Note): pass

@children(Child1, Child2) # add children with no branch prefix
@child(Child3, prefix="My prefix") # add child with branch prefix
class Parent(Note): pass
```

## Custom initializer to add attributes, children

Define {obj}`Note.init` or {obj}`Mixin.init` to add attributes and children dynamically. Use the following APIs to add attributes and children:

- {obj}`Note.create_declarative_label`
- {obj}`Note.create_declarative_relation`
- {obj}`Note.create_declarative_child`

These APIs are required for singleton notes to generate a deterministic id for attributes and children, generating the same subtree every time the {obj}`Note` subclass is instantiated.

For example, a mixin which provides a convenient way to set an attribute `#myLabel` to a given value:

```python
class MyMixin(Mixin):

    my_label: str | None = None
    """
    If set, add attribute `myLabel` with provided value.
    """

    def init(self, attributes: list[Attribute], children: list[Branch]):
        if self.my_label:
            attributes.append(
                self.create_declarative_label("myLabel", self.my_label)
            )

class MyNote(Note, MyMixin):
    """
    This note will automatically have the label `#myLabel=my-label-value`.
    """

    my_label = "my-label-value"
```

(leaf-notes)=
## Leaf notes

If you design a note hierarchy using this approach, you might want to designate some "folder" notes to hold user-maintained notes. Set {obj}`Note.leaf` or {obj}`Mixin.leaf` to indicate this, in which case using {obj}`children` or {obj}`child` will raise an exception.

For example, this would be necessary for a list of contacts:

```python
@label("sorted")
@label("iconClass", "bx bx-group")
class Contacts(Note):
    singleton = True
    leaf = True
```

Now, assuming it's been placed in your hierarchy, you can access your contact list by simply instantiating `Contacts`.
