(working-with-attributes)=
# Attributes

## Owned and inherited attributes

Combined owned and inherited attributes are accessed as: {obj}`Note.attributes`

Access as a list:

```python
# add some attributes
note.attributes.append(Label("myLabel"))
note.attributes.append(Relation("myRelation", session.root))

for attr in note.attributes:
    print(f"Attribute: {attr}")
```
```none
Attribute: Label(#myLabel, value=, attribute_id=None, note=Note(title=new note, note_id=None), position=10)
Attribute: Relation(~myRelation, target=Note(title=root, note_id=root), attribute_id=None, note=Note(title=new note, note_id=None), position=20)
```

Index by attribute name, getting a list of attributes with that name:

```python
# add a label
note += Label("myLabel")

print(note.attributes["myLabel"][0])
```
```none
Label(#myLabel, value=, attribute_id=None, note=Note(title=new note, note_id=None), position=10)
```

Use `in`{l=python} to check if an attribute exists by name:

```python
assert "myLabel" in note.attributes
```

When an attribute is deleted from the list, it's automatically marked
for delete:

```python
# add a label
label = Label("myLabel")
note += label

# delete from list
del note.attributes[0]

print(f"label.state: {label.state}")
```
```none
label.state: State.DELETE
```

Assign a new list, deleting any existing attributes not in the list:

```python
# add a label
label1 = Label("myLabel1")
note += label1

# assign a new list of attributes
label2 = Label("myLabel2")
note.attributes = [label2]

print(f"label1.state: {label1.state}")
print(f"label2.state: {label2.state}")
```
```none
label1.state: State.DELETE
label2.state: State.CREATE
```

## Owned attributes

Owned attributes are accessed as: {obj}`OwnedAttributes <Note.attributes.owned>`. Implements the same interface as {obj}`Attributes`.

## Inherited attributes

Inherited attributes are accessed as: {obj}`InheritedAttributes <Note.attributes.inherited>`. Implements the same interface as {obj}`Attributes`.
