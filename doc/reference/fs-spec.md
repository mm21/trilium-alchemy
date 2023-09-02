(fs-spec)=
# Filesystem note specification (in progress)

This describes a specification for a Trilium note tree captured by a filesystem. See {ref}`filesystem-notes` for a tutorial-style discussion of this concept.

In general, this specification is similar to Trilium's .zip export format. However there are key differences, as this specification is designed to be manually maintainable. It's human-friendly rather than machine-friendly, and a little more work is required to parse this format as a result.

## Reserved folder and file names

Folder and file names beginning with `!` are reserved for system use.

## Sync context

The **sync context** is comprised of a number of **sync mappings** along with a **sync state**. It has a root folder, **sync root**, on the filesystem.

### Sync endpoints

A **sync endpoint** specifies a note subtree which can be synchronized. It may be any of the following:

- A note belonging to a Trilium instance, specified by connection info and `noteId` or a label (e.g. `#myRoot`)
- A folder on the local filesystem (**sync root** or a subdirectory thereof)

### Sync mappings

A **sync mapping** specifies a mapping between multiple **sync endpoint**s. It has an associated **sync mode**:

- **Mirror**: Map source to destination endpoint, overwriting the destination state to match the source
- **Resolve**: Resolve changes in all endpoints compared to the last sync operation

### Sync state

For mappings with mode **resolve**, the combined metadata (including content signatures) from the last sync operation is required to persist from one invocation to the next. This is known as the **sync state**. It will be stored in text format, tentatively called `!sync.json` (not unlike Trilium's zip format `!!!meta.json`). It is not expected to be maintained manually, but stored as text to be readily usable in version control.

## Notes as folders

Every folder maps to a note in Trilium. Child files and folders are treated as child notes.

## Notes as files

A file with name not beginning with `!` is considered a child of the note represented by the parent folder.

A folder with the same name as this file with a single `!` prepended is reserved to contain children of the note represented by this file. For example, children of `Hello world.md` are stored in the folder `!Hello world.md`.

### `#originalFilename` label

The label `#originalFilename` is automatically maintained for file-based notes. When a note with this label is synced from Trilium to a folder, it's replicated as a file-based note using this filename.

Therefore this label must generally be unique for each child of a given parent note. If there are multiple notes with the same value of `#originalFilename` belonging to the same parent, the sync invocation will fail.

The filename of the file-based note and `#originalFilename` label are automatically kept in sync.

## Metadata

Note metadata is stored in YAML format. Placement of the YAML document depends on note type and sync configuration.

### YAML source

#### Folder notes: `!meta.yaml`

For folder-based notes, metadata is provided in `!meta.yaml`.

#### File notes: `*.!meta.yaml`

For file-based notes, metadata is provided alongside the file. The name of the metadata file is the name of the file suffixed with `.!meta.yaml`.

#### Markdown notes: Frontmatter

For `*.md` file-based notes, frontmatter can be utilized to provide a more concise representation of the note if `*.!meta.yaml` is not provided. This may be optionally disabled, either globally or per note (mechanism TBD).

### Fields (title/type/mime)

Unless explicitly provided in the metadata, title is derived based on how the note is specified:

- Folder note: folder name
- File note: **base name** of the file (e.g. `Hello world.md` would have the title `Hello world`).

For simplicity, multiple child notes with the same title are currently not allowed. There may be a future mechanism to accommodate this, e.g. appending title with a suffix like `!2`.

For file-based notes, `type` and `mime` are by default derived from the file. They may be explicitly set in the metadata YAML.

Some other fields are derived, e.g. attribute and child note positions are not explicitly set. The order is optionally provided by the user (defaulting to alphabetical), but position values are calculated rather than maintained by the user.

### Attributes

Attributes are similarly captured in `!meta.yaml`. Attribute `type` is inferred by whether the attribute is specified with `value` (for type `label`) or `target` note (for type `relation`).

For ease of maintenance, `attributeId` is not maintained manually. The synchronization algorithm resolves attributes agnostic of `attributeId`.

## Note id

To reliably compare note state with Trilium, `noteId` is required to be defined for each filesystem-based note. If not explicitly provided in metadata, it's derived from the path relative to **sync root**.

### Provided `noteId`

`noteId` can be explicitly provided in `!meta.yaml`. Notes originally synced from Trilium will have `noteId` fixed in this way.

### Provided `noteIdSeed`

If `noteIdSeed` is provided in `!meta.yaml`, this value is used to generate `noteId` as the SHA-256 hash of `noteIdSeed`, base64-encoded (with replacement of `+` and `/`).

### Filename as seed

If neither `noteId` nor `noteIdSeed` is provided, `noteIdSeed` is taken to be the path of the file or folder representing this note, prefixed with its parent's `noteIdSeed` if not a top-level child of **sync root**.

### Note links in Markdown

This allows referencing of notes in a flexible and maintainable way. For example, a note could be referenced in a Markdown file in the following ways:

```markdown
- [Related note with noteIdSeed specified](noteIdSeed:my-note-1)
    - [Child without noteIdSeed specified](noteIdSeed:my-note-1/a.md)
- [Related note without noteIdSeed specified](noteIdSeed:/path/to/my-note-2.md)
```

If not leading with `/`, the path provided is relative to the current note's path. The full path relative to **sync root** (with a leading `/`) is formed prior to computing the hash.

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

A given note is required to be defined in exactly one filesystem location - its **canonical path**. If the note is initially created on a filesystem, this is the canonical path. If being newly written from a Trilium server, a note path will be chosen (algorithm TBD) to contain the filesystem representation, while the others will be considered as clones.

### Clone notes

A clone is created as a text file named `!clone.[noteId].yaml`. It optionally contains branch parameters like `prefix`. Its position relative to other children is specified by providing the filename in the parent's `children` list, same as for other children.
