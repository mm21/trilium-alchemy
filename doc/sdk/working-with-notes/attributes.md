(working-with-attributes)=
# Attributes

As mentioned in {ref}`working-with-notes-notes`, one or more attributes can be added to a note via the `+=` operator:

```python
note += Label("myLabel")
note += [Label("myLabel2", "myValue2"), Relation("myRelation", other_note)]
```

The following sections describe other interfaces to access attributes.

## Single-valued labels

Notes can be indexed to get/set an owned single-valued label, or specifically the first owned label matching the provided name. If no owned label with that name exists, a new one is created.

For example, to set `#priority=10`:

```python
assert "priority" not in note

note["priority"] = "10"

assert "priority" in note
assert note["priority"] == "10"
```

{obj}`Note` does not implement a fully-featured dictionary, only dictionary-like semantics for single-valued labels.

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

- {obj}`Note.labels.owned <trilium_alchemy.core.note.attributes.OwnedLabels>`
- {obj}`Note.labels.inherited <trilium_alchemy.core.note.attributes.InheritedLabels>`

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

- {obj}`Note.relations.owned <trilium_alchemy.core.note.attributes.OwnedRelations>`
- {obj}`Note.relations.inherited <trilium_alchemy.core.note.attributes.InheritedRelations>`

## Combined labels and relations

The combined list of labels and relations is accessed as: {obj}`Note.attributes`. It provides an interface similar to {obj}`Note.labels` and {obj}`Note.relations`.

To filter by owned vs inherited, use:

- {obj}`Note.attributes.owned <trilium_alchemy.core.note.attributes.OwnedAttributes>`
- {obj}`Note.attributes.inherited <trilium_alchemy.core.note.attributes.InheritedAttributes>`

```{note}
Implementation detail: The latter two objects constitute the source of truth for attributes; all other interfaces simply map to these while providing type correctness.
```
