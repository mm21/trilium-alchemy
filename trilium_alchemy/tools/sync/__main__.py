"""
CLI tool to sync mappings of local sources with notes in Trilium.

A local resource may be any of:

- Folder hierarchy of Markdown, HTML or other files
    - User can provide a parser which generates notes from a file/folder
        - Example: parse a folder documenting a trip into a note with ~template=Trip,
        individual days (separate .md file) added as child notes
        - TODO: MyST parser?
        - TODO: Write only - no conversion from HTML back to Markdown?
- Path to zip file (e.g. extension)
- Folder containing a zip file (e.g. a cloned repository for an extension)
- GitHub URL (automatically clones and manages repo, e.g. runs `git pull` to update)

If the local mapping is provided as a list, entries are added as children 
of the destination note. Otherwise, the provided resource is synchronized
directly to the destination (not as a child).

A destination note may be identified by:

- Label, e.g. `#extensionsRoot`
- Note's `note_id`, e.g. `root`
- Fully qualified class name of singleton {obj}`Note` subclass, e.g. 
`my_notes.contacts.Contacts`

The "mode" (`push` or `sync`) is inferred by the way the nodes are specified:

- `dest` and `src`: `mode = "push"` from `src` to `dest`
- `nodes`: `mode = "sync"`

Mode affects the direction of the sync:
- `push`: Replicate source to destination, overwriting any 
existing destination
    - If source is a Trilium note and destination is a .zip, exports to zip 
    format
    - If source is a .zip and destination is a Trilium note, imports from zip
    format
- `sync`: Synchronize source to destination, automatically resolving
    - Sync state (possibly pickled Python objects) is required
        - Contains metadata of subtree upon last sync
    - If there are any conflicts, the sync will fail and inform the user of
    the conflicting state - e.g. if an attribute value was changed in both nodes
    since the last sync
"""
