(fs-spec)=
# Filesystem note specification (in progress)

This document describes a specification for representing a Trilium note tree using a filesystem. See {ref}`filesystem-notes` for API access to this interface.

In general, this specification is similar to Trilium's .zip export format. However there are key differences as this is designed to be manually maintainable. It's intended to be human-friendly rather than machine-friendly, and more work is required to parse it as a result.

## Intro

### Motivation

Trilium is fundamentally more powerful than a filesystem for categorizing information. Nonetheless, it can be valuable to maintain core sources of truth in a traditional filesystem format. This allows the use of powerful and familiar tools such as `git` to track changes, and convenient (though less rich than Trilium itself) offline access to one's information. Trilium is then viewed as an engine to "hydrate" this information, providing a UI for it and visualizing its relationship with other information.

In particular, this system should provide first-class support for Markdown notes by utilizing YAML frontmatter to contain Trilium's metadata.

### Existing solutions

% TODO

## Constraints

Some simplifying assumptions are made for filesystem representation.

If a given subtree fails to meet these requirements, attempting to synchronize it with a filesystem will fail with an error prior to changing any state.

### Trilium subtree

- Child note titles must be unique
    - An enhancement may be developed in the future to accommodate duplicate titles
- Label `#originalFilename` must be unique for child notes

### Filesystem subtree

- Folder and file names beginning with `!` are reserved for system use

## Sync context

The **sync context** is comprised of a number of **sync mappings** from one **sync endpoint** to another. It has a root folder, **sync root**, on the filesystem.

There is a configuration file, by default `!context.yaml` placed in **sync root**.

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

## Filesystem representation

Filesystem representation of a note is determined by whether or not it has an `#originalFilename` label.

### File-based notes

A note is condiered file-based if and only if it has an `#originalFilename` label. A file-based note is a child of the note represented by its containing folder. 

The `#originalFilename` label is managed as follows:

- Created automatically upon synchronizing an existing folder tree
- Filename is updated to reflect the label value, if changed
- Label value is updated to reflect the filename, if changed

A folder named as the filename prepended with a single `!` is reserved to contain children of the note represented by this file. For example, children of `Hello world.md` are stored in the folder `!Hello world.md`.

### Folder-based notes

A note is considered folder-based if and only if it does not have an `#originalFilename` label. Child files and folders are interpreted as child notes.

## Note id

To reliably compare note state with Trilium, `noteId` is required to be defined for each filesystem-based note. If not provided in metadata, it's initially generated based on the current timestamp.

```{todo}
Allow Trilium to generate `noteId`? Would require extra handling to update filesystem `noteId`, and ensuring Trilium subtree is flushed first.
```

### Provided `noteId`

`noteId` can be explicitly provided in `!meta.yaml`. Notes originally synced from Trilium will have `noteId` fixed in this way.

### Provided `noteIdSeed`

If `noteIdSeed` is provided in `!meta.yaml`, this value is used to generate `noteId` as the SHA-256 hash of `noteIdSeed`, base64-encoded with replacement of `+` and `/`.

## Metadata

Note metadata is stored in YAML format. Placement of the YAML document depends on note type and sync configuration.

### YAML source

#### Folder notes: `!meta.yaml`

For folder-based notes, metadata is provided in `!meta.yaml`.

#### File notes: `*.!meta.yaml`

For file-based notes, metadata is provided alongside the file. The name of the metadata file is the name of the file suffixed with `.!meta.yaml`. For example, metadata for `photo001.jpg` is stored in `photo001.jpg.!meta.yaml`.

#### Markdown notes: Frontmatter

For `*.md` file-based notes, frontmatter can be utilized to provide a more concise representation of the note if `*.!meta.yaml` is not provided. This may be optionally disabled, either globally or per note (mechanism TBD).

### Title

To avoid duplication of information, title is inferred based on how the note is specified:

- Folder-based note: folder name
- File-based note: **base name** of the file (e.g. `Hello world.md` would have the title `Hello world`)

For simplicity, multiple child notes with the same title are currently not allowed. There may be a future mechanism to accommodate this, e.g. appending title with a suffix like `~2`.

```{todo}
Generate filesystem path as slug of title? (could also enable duplicate titles)
```

### Type, MIME

For file-based notes, `type` and `mime` are derived from the file itself if not specified in the metadata YAML.

### Position values

Attribute and child note positions are not explicitly specified. The order is optionally provided by the user (defaulting to alphabetical for children not listed), but position values are inferred rather than explicitly maintained by the user.

### Attributes

Attributes are specified as a list of strings in `!meta.yaml`. Attribute `type` is inferred by the first character: `~` implies a relation, otherwise it's interpreted as a label.

For ease of maintenance, `attributeId` is not specified. The synchronization algorithm resolves attributes agnostic of `attributeId`.

#### Maintenance of `#filesystemPath` label

If configured, notes can be labeled with the path to their file/folder representation relative to the **sync root**.

This allows referencing of notes in a flexible and maintainable way. For example, a note could be referenced in a Markdown file as follows:

```markdown
- [Related note relative to current file](filesystemPath:note-1.md)
- [Related note with noteIdSeed specified](noteIdSeed:my-note-1)
```

If not leading with `/`, the path provided is relative to the current note's path. The full path relative to **sync root** (with a leading `/`) is inferred.

A Markdown renderer widget in Trilium's UI could then resolve the target `noteId` to generate a link by either searching for the provided label or using the provided `noteIdSeed` to compute it. Such a widget is currently in development and will be provided along with this framework.

## Content

Content is stored based on how the note is specified:

- File-based note: in the file with name given by `#originalFilename`
- Folder-based note: in `!content.*`, where the extension is based on the note's `type` and `mime` fields
    - For example, `text/html` notes would have content stored in `!content.html`

## Children

The order of children may be specified in YAML metadata, along with an optional branch prefix. Not all children are required to be listed. Children listed in YAML metadata are positioned first, followed in alphabetical order by those not listed.

If only some children are listed in YAML metadata, those are placed in the order provided at the beginning of the child list. Those not specified are sorted alphabetically at the end of the provided list.

## Clones

### Canonical notes

A given note is required to be defined in exactly one filesystem path - its **canonical path**. If the note is initially created on a filesystem, this is the canonical path. If being newly written from a Trilium server and the path is ambiguous due to notes having multiple parents, a note path will be chosen (algorithm TBD) to contain the filesystem representation. Other branches will be considered as clones.

As mentioned previously, the `#filesystemPath` label can optionally be maintained to reflect its **canonical path**.

### Clone notes

A clone is created as a text file named `!clone.[noteId].yaml`. It optionally contains branch parameters like `prefix`. Its position relative to other children is specified by providing the filename in the parent's `children` list, same as for other children.
