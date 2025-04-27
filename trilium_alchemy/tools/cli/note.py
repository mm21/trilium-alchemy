"""
Operations on one or more notes, not necessarily within the same subtree.

Options to select note(s): (exactly one required)
- --note-id: str | None = None
- --search: str | None = None
- --all: bool = False
    - Apply operation on all notes, or all applicable notes depending on command

Commands:
- sync-template: syncs previously selected notes with this template,
    all notes w/this template if --all; verifies template note has #template
    or #workspaceTemplate
    --template-note-id
    --template-search
    --all-templates
    --dry-run
    -y/--yes
"""
