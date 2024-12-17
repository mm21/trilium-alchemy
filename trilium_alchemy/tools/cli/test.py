"""
CLI command to generate test notes. Uses an algorithm to generate a configurable 
amount of test notes with a configurable hierarchy depth.

If there are N notes per level and depth D > 0, the total number of notes 
generated is:

N^1 + N^2 + ... + N^D

For example, use D=2 levels of N=10 notes to generate 110 notes:
- 10 root (level 0) notes
- 100 level 1 notes (10 for each root note)

Use D=5, N=10 to generate 111110 notes, which is around what Trilium is expected
to be able to handle.

Use D=6, N=10 to generate 1111110 notes, over 1 million.
"""
