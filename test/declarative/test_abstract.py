"""
Test cases for "abstract" (declarative, non-singleton) note trees. There 
are 2 use cases for these:

1. Deterministic note trees: don't have a note_id until "anchored" to a note 
with a known id. Then the notes in the abstract tree are assigned the same id 
every time the tree is instantiated.

Useful for note hierarchies which can be reused in separate note instances.

2. Note tree "template" which creates new instances upon being instantiated, 
e.g. in automation.

TODO:
Both of these cases are covered in tests already, but it would be good to
cover them explicitly here.
"""
