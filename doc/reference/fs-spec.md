(fs-spec)=
# Filesystem note specification (in progress)

This describes a specification for a Trilium note tree captured by a filesystem. See {ref}`filesystem-notes` for a tutorial-style discussion of this concept.

In general, this specification is similar to Trilium's .zip export format. However there are key differences, as this specification is designed to be manually maintainable. It's human-friendly rather than machine-friendly, and a little more work is required to parse this format as a result.

## Reserved folder and file names

Folder and file names beginning with `!` are reserved for system use.

## Synchronization context and state

A folder root is mapped to a destination note in Trilium. This mapping, along with the associated state, is called a **sync context**. There may be many sync contexts specified in a single synchronization invocation. 

The combined metadata (including content signatures) of the last synced tree is required to persist from one synchronization invocation to the next. This is known as the **sync state**. It will be stored in a text file (not unlike Trilium's zip format `!!!meta.json`, but file type TBD). It is not expected to be maintained manually, but stored as text to be readily usable in version control.

## Notes as folders

Every folder maps to a note in Trilium. Child files and folders are treated as child notes.

## Notes as files

A file with name not beginning with `!` is considered a child of the note represented by the parent folder.

A folder with the same name as this file, but with a single `!` prepended, is reserved to contain children and metadata of the note represented by this file. For example, metadata and children for `Hello world.md` are stored in the folder `!Hello world.md`. This corresponding folder is created automatically upon the first synchronization invocation.

Therefore every note is represented as a folder, even if the content is specified from a file. There is some extra maintenance for file-based notes as their names are required to align with the folder containing their children and metadata.

## Metadata

Note metadata is stored in YAML format. Placement of the YAML document depends on note type and configuration.

### YAML source

#### Markdown frontmatter

For `.md` files, frontmatter is utilized to provide a more concise representation of the note.

#### `!meta.yaml`

In the note folder (filename appended with `!` for file notes) there can be a file called `!meta.yaml`. If provided, this is used in place of frontmatter for `.md` file notes.

### Fields (title/type/mime)

Title is derived based on how the note is specified:

- Folder note: folder name
- File note: **base name** of the file (e.g. `Hello world.md` would have the title `Hello world`).

For children with the same title, the folder will be appended with `!2`, `!3`, etc.

For file-based notes, `type` and `mime` are by default derived from the file information. They may be explicitly set the metadata YAML.

Some other fields are derived, e.g. attribute and child note positions are not explicitly set. The order is optionally provided by the user (defaulting to alphabetical), but position values are calculated rather than maintained by the user.

### Attributes

Attributes are similarly captured in `!meta.yaml`. Attribute `type` is inferred by whether the attribute is specified with `value` (for type `label`) or `target` note (for type `relation`).

For ease of maintenance, `attributeId` is not maintained manually. The synchronization algorithm resolves attributes agnostic of `attributeId`.

## Note id

% discussion of why noteId is required to be defined for each filesystem note

### Provided `noteId`

`noteId` can be explicitly provided in `!meta.yaml`. Notes originally synced from Trilium will have `noteId` fixed in this way.

### Provided `noteIdSeed`

If `noteIdSeed` is provided in `!meta.yaml`, this value is used to generate `noteId`. It's expected to be computed as the SHA-256 hash of `noteIdSeed`, base64-encoded (with replacement of `+` and `/`).

### Filename as seed

If neither `noteId` nor `noteIdSeed` is provided, `noteIdSeed` is taken to be the path of the file or folder representing this note relative to its parent's `noteIdSeed`. 

### Note links in Markdown

This allows referencing of notes in a flexible and maintainable way. For example, a note could be referenced in a Markdown file in the following ways:

```markdown
- [Related note with noteIdSeed specified](noteIdSeed:my-note-1)
    - [Child without noteIdSeed specified](noteIdSeed:my-note-1/a.md)
- [Related note without noteIdSeed specified](noteIdSeed:path/to/my-note-2.md)
```

A Markdown renderer widget in Trilium's UI could then resolve `noteId` and generate a link to the target note. Such a widget is currently in development and will be provided along with this framework.

## Content

Content is populated based on how the note is specified:

- Folder note: content is stored in `!content.*`, where the extension is based on the note's `type` and `mime` fields
    - For example, `text/html` notes would have content stored in `!content.html`
- File note: content is stored in the file itself

## Children

The order of children may be specified in YAML metadata, along with an optional branch prefix. Not all children are required to be listed. Children listed in YAML metadata are positioned first, followed in alphabetical order by those not listed.

If only some children are listed in YAML metadata, those are placed in the order provided at the beginning of the child list. Those not specified are sorted alphabetically at the end of the provided list.

## Clones

### Canonical notes

A given note is required to be defined in exactly one filesystem location - its **canonical path**. If the note is initially created on a filesystem, this is the canonical path. If being newly written from a Trilium server, a note will be chosen (algorithm TBD) to contain the filesystem representation, while the others will be considered as clones.

### Clone notes

A clone is created as a text file named `!clone.*.yaml`. It contains a reference to the **canonical path**, specified relative to the **sync context** root, and optionally branch parameters.
