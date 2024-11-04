# Branches

## Parent and child branches

Combined parent and child branches are accessed as: {obj}`Note.branches`.

When iterated, yields from parent branches (sorted by{obj}`id() <id>`) and then child branches (sorted by {obj}`Branch.position`).

```python
# add root as parent of note
note ^= session.root

# create child note
note += Note()

# iterate over branches
for branch in note.branches:
    print(branch)
```

```none
Branch(parent=Note(title=root, note_id=root), child=Note(title=new note, note_id=None), prefix=, expanded=False, position=1000000009, branch_id=None)
Branch(parent=Note(title=new note, note_id=None), child=Note(title=new note, note_id=None), prefix=, expanded=False, position=10, branch_id=None)
```

## Parent branches

Parent branches are accessed as: {obj}`ParentBranches <Note.branches.parents>`.

Modeled as a {obj}`set` as parent branches are not inherently ordered, but serialized by {obj}`id() <id>` when iterated.

When a {obj}`Note` is added to the set, a parent {obj}`Branch` is automatically created.

## Child branches

Child branches are accessed as: {obj}`ChildBranches <Note.branches.children>`.

Modeled as a {obj}`list` of branches ordered by {obj}`Branch.position`.

When a {obj}`Note` is added to the list, a child {obj}`Branch` is automatically created.

## Parent notes

Parent notes are accessed as: {obj}`Note.parents`.

## Child notes

Child notes are accessed as: {obj}`Note.children`
