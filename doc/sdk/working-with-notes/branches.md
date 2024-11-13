# Branches

## Parent branches

Parent branches are accessed as: {obj}`ParentBranches <Note.branches.parents>`.

Modeled as a {obj}`set` as parent branches are not inherently ordered, but serialized by {obj}`id() <id>` when iterated.

When a {obj}`Note` is added to the set, a parent {obj}`Branch` is automatically created.

## Child branches

Child branches are accessed as: {obj}`ChildBranches <Note.branches.children>`.

Modeled as a {obj}`list` of branches ordered by {obj}`Branch.position`. Position is maintained automatically; you can simply reorder the list itself as desired.

When a {obj}`Note` is added to the list, a child {obj}`Branch` is automatically created.

## Combined parent and child branches

Combined parent and child branches are accessed as: {obj}`Note.branches`.

When iterated, yields from parent branches followed by child branches.

## Parent notes

Parent notes are accessed directly as: {obj}`Note.parents`.

## Child notes

Child notes are accessed directly as: {obj}`Note.children`.
