(fs-spec)=
# Filesystem note specification (in progress)

This describes a specification for a Trilium note tree captured by a filesystem. See {ref}`filesystem-notes` for a tutorial-style discussion of this concept.

In general, this specification is similar to Trilium's .zip export format. However there are key differences, as this specification is designed to be manually editable. It's human-friendly rather than machine-friendly, and a little more work is required to parse this format as a result.

## Reserved folder and file names

Folder and file names beginning with `!` are reserved for system use.

## Synchronization context and state

A folder root is mapped to a destination note in Trilium. This mapping is called a **sync context**. There may be many such contexts specified in a single synchronization invocation. 

The combined metadata (including note content signatures) of the last synced tree is required to persist from one synchronization invocation to the next. This is known as the **sync state**. It will be stored in a text file (not unlike Trilium's zip format `!!!meta.json`, but file type TBD). It is not expected to be maintained manually, but stored as text to be readily usable in version control.

## Notes as folders

Every folder maps to a note in Trilium. Child files and folders are treated as child notes.

## Notes as files

A file with name not beginning with `!` is considered a child of the note represented by the parent folder.

A folder with the same name as this file, but with a single `!` prepended, is reserved to contain children and metadata of the note represented by this file. For example, metadata and children for `Hello world.md` are stored in the folder `!Hello world.md`. This corresponding folder is created automatically upon the first synchronization invocation.

Therefore every note is represented as a folder, even if the content is specified from a file. There is some extra maintenance for file-based notes as their names are required to align with the folder containing their children and metadata.

## Note id

### Provided `noteId`

`noteId` can be explicitly provided in `!meta.yaml`. Notes synced from Trilium will have `noteId` fixed in this way.

### Deterministic `noteId`

If `noteId` is not explicitly provided, it's derived based on the relative path of the file or folder representing the note. This allows referencing of notes in a maintainable way, without requiring the user to manually keep track of `noteId`. For example, a note could be referenced in a Markdown file as follows:

```markdown
- [Related note](path/to/related-note.md)
```

To compute `noteId`, the full path to the note file is formed relative to the **sync context** root. This will then be hashed and base64-encoded to form `noteId`.

A Markdown renderer widget in Trilium's UI could then resolve `noteId` and generate a link to the target note. Such a widget is currently in development and will be provided along with this framework.

## Metadata

Note metadata is stored in YAML format per note folder in a file called `!meta.yaml`. An initial `!meta.yaml` is populated upon the first synchronization invocation.

### Fields (title/type/mime)

Title is derived based on how the note is specified:

- Folder note: folder name
- File note: **base name** of the file (e.g. `Hello world.md` would have the title "Hello world").

For children with the same title, the folder will be appended with `!2`, `!3`, etc.

`type` and `mime` are by default derived from the file information, for file-based notes. They may be explicitly set in `!meta.yaml`.

Some other fields are derived, e.g. there's no manual specification of attribute and child note positions. The order is optionally provided by the user (defaulting to alphabetical), but position values are calculated rather than maintained by the user.

### Attributes

Attributes are similarly captured in `!meta.yaml`. Attribute `type` is inferred by whether the attribute is specified with `value` (for type `label`) or `target` note (for type `relation`).

## Content

Content is populated based on how the note is specified:

- Folder note: content is stored in `!content.*`, where the extension is based on the note's `type` and `mime` fields
    - For example, `text/html` notes would have content stored in `!content.html`
- File note: content is stored in the file itself

## Children

The order of children may be specified in `!meta.yaml`, along with an optional branch prefix. Not all children are required to be listed. Children listed in `!meta.yaml` are positioned first, followed in alphabetical order by those not listed.

## Clones

### Canonical notes

A given note is required to be defined in exactly one filesystem location - its **canonical path**.

### Clone notes

A clone is created as a text file named `!clone.*.yaml`. It contains a reference to the **canonical path**, relative to its location or to the **sync context** root, and optionally branch parameters.
