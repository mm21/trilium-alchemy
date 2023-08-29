(fs-spec)=
# Filesystem note specification (in progress)

This describes a specification for a Trilium note tree captured by a filesystem. See {ref}`filesystem-notes` for a tutorial-style discussion of this concept.

In general, this specification is similar to Trilium's .zip export format. However there are key differences, as this specification is designed to be manually editable. It's human-friendly rather than machine-friendly, and a little more work is required to parse this format as a result.

## Synchronization context and state

A folder root is mapped to a destination note in Trilium. This mapping is called a **sync context**. There may be many such contexts specified in a single synchronization invocation. 

The combined metadata (including note content signatures) of the last synced tree is required to persist from one synchronization invocation to the next. This is known as the **sync state**.

## Notes as folders

Every folder maps to a note in Trilium. Child files and folders are treated as child notes.

## Notes as files

A file with name not beginning with `!` is considered a child of the note represented by the parent folder.

A folder with the same name as this file, but with a single `_` appended, is reserved to contain children and metadata of the note represented by this file. For example, metadata and children for `Hello world.md` are stored in the folder `Hello world.md_`. This corresponding folder is created automatically upon the first synchronization invocation.

Therefore, every note is represented as a folder. There is some extra maintenance for file-based notes as their names are required to align with the folder containing their children and metadata.

## Note id generation

To reference other notes in a maintainable way, `noteId` needs to be generated based on the relative path of the file or folder representing the note. Then, for example, a note could be referenced in a Markdown file as follows:

```markdown
- [Related note](path/to/related-note.md)
```

To compute `noteId`, the full path to the note file is formed relative to the **sync context** root. This will then be hashed and base64-encoded to form `noteId`.

A Markdown renderer widget could resolve `noteId` and generate a link to the target note.

## Metadata

Note metadata is stored in YAML format per note folder in a file called `!meta.yaml`. An initial `!meta.yaml` is populated upon the first synchronization invocation.

### Fields (title/type/mime)

Title is inferred based on how the note is specified:

- Folder note: The folder name
- File note: the **base name** of the file (e.g. `Hello world.md` would have the title "Hello world").

For children with the same title, the folder will be appended with `---2`, `---3`, etc.

Some state is inferred, e.g. there's no manual specification of attribute and child note positions. The order is optionally provided by the user (defaulting to alphabetical), but position values are calculated rather than maintained by the user.

### Attributes

Attributes are similarly captured in `!meta.yaml`.

## Content

Content is populated from the file itself for file-based notes. For folder-based notes, content is stored in `!content.*`, where the extension is based on the note's `type` and `mime` fields. For example, `text/html` notes would have content stored in `!content.html`.

## Children

The order of children may be specified in `!meta.yaml`, along with an optional branch prefix.

## Clones

Clones are created as text files named as `!clone.*.yaml`. They contain a reference to the **canonical** note path, relative to the **sync context** root.
