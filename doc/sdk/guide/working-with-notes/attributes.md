(working-with-attributes)=
# Attributes

One or more attributes can be added to a note via the `+=` operator:

```python
note += Label("myLabel")
note += [Label("myLabel2", "myValue2"), Relation("myRelation", other_note)]
```

The following sections describe interfaces to access attributes.

## Single-valued labels

Single-valued labels can be created, updated, or retrieved by indexing into the note itself:

```python
assert "priority" not in note

note["priority"] = "10"

assert "priority" in note
assert note["priority"] == "10
```

## Labels

Labels are accessed as {obj}`Note.labels`. For example, to get/set the first label with a given name:

```python
assert "myLabel" not in note.labels
assert note.labels.get_value("myLabel") is None

note.labels.set_value("myLabel", "myValue1")

assert "myLabel" in note.labels
assert note.labels.get_value("myLabel") == "myValue1"
```

To get all labels with a given name:

```python
assert len(note.labels.get_all("myLabel")) == 1
assert note.labels.get_values("myLabel") == ["myValue1"]
```

To filter by owned vs inherited, use:

- {obj}`OwnedLabels <Note.labels.owned>`
- {obj}`InheritedLabels <Note.labels.inherited>`

## Relations

Relations are accessed as {obj}`Note.relations`. For example, to get/set the first relation with a given name:

```python
assert "myRelation" not in note.relations
assert note.relations.get_target("myRelation") is None

note.relations.set_target("myRelation", other_note)

assert "myRelation" in note.relations
assert note.relations.get_target("myLabel") is other_note
```

To get all relations with a given name:

```python
assert len(note.relations.get_all("myRelation")) == 1
assert note.relations.get_targets("myRelation") == [other_note]
```

To filter by owned vs inherited, use:

- {obj}`OwnedRelations <Note.relations.owned>`
- {obj}`InheritedRelations <Note.relations.inherited>`

## Combined labels and relations

The combined list of labels and relations is accessed as: {obj}`Note.attributes`. It provides an interface similar to {obj}`Note.labels` and {obj}`Note.relations`.

To filter by owned vs inherited, use:

- {obj}`OwnedAttributes <Note.attributes.owned>`
- {obj}`InheritedAttributes <Note.attributes.inherited>`
