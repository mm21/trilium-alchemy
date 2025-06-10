# CLI

The CLI tool `trilium-alchemy` manages Trilium by building on core SDK functionality.

## Configuration

The tool can be configured via any of the following, in order of precedence:

- `.yaml` file
  - Supports multiple Trilium instances
- Command-line options
- Environment variables
- `.env` file

### Config file example

```yaml
# optional top-level data dir with subfolders per instance
root_data_dir:
  "./trilium_data"

# mapping of instance names to info
instances:
  my-notes:
    # connection info, either "token" or "password" required
    host: "http://localhost:8080"
    token: "MY_TOKEN"
    password: "MY_PASSWORD"

    # optional data dir which overrides root_data_dir/[instance]
    data_dir: "./my-notes-data"

    # optional fully-qualified class name of root note for tree push
    root_note_fqcn: "my_notes.root.RootNote"
```

## Filesystem note format

The CLI represents Trilium notes on the filesystem using a prefix tree structure designed for efficient storage and retrieval of large note collections. As Trilium is intended to scale to 100,000+ notes, this format is designed to scale accordingly.

For more background on Trilium's scaling capability, see the documentation on [Scalability](https://github.com/TriliumNext/trilium/wiki/Patterns-of-personal-knowledge-base#scalability):

>My rule of thumb for estimation of size of personal knowledge base is that you can reasonably produce around 10 notes a day, which is 3650 in a year. I plan to use my knowledge base long term (with or without Trilium Notes), probably decades so you can easily get to number 100 000 or even more. Right now, my personal knowledge base has around 10 000 notes.
>
>100 000 is a number to which most note taking software doesn't scale well (in both performance and UI). Yet I don't think it's really very much considering a lifetime of knowledge.

### Design goals

This format is designed with the following goals in mind:

- **Source control friendliness**: Note metadata should be stored as text while preserving the exact information captured in Trilium
- **Diff minimization**: A single change in the UI (e.g. reordering a child note or adding an attribute) should ideally result in a single line changed in the filesystem representation
- **Human readability**: While the filesystem format is not necessarily intended to be edited by hand, it should be accessible upon inspection and feasible to modify, either manually or via external software

### Directory structure

Notes are organized in a hierarchical prefix tree with 2 levels of depth:

```
/dump_root/
├── a1/
│   ├── b2/
│   │   ├── c3d4e5f6g7h8i9j0k1l2m3n4o5p6/
│   │   │   ├── meta.yaml
│   │   │   └── content.txt
│   │   └── x9y8z7w6v5u4t3s2r1q0p9o8n7m6/
│   │       ├── meta.yaml
│   │       └── content.bin
│   └── b3/
│       └── ...
└── a2/
    └── ...
```

Each note is stored in a folder named using a hash of its note ID:

- **Prefix levels**: 2 levels of 2-character hex prefixes (e.g., `a1/b2/`)
- **Note folder**: 28-character hex suffix containing the note's files

### Rationale for prefix tree

The prefix tree structure provides several benefits:

- **Case-insensitive filesystem compatibility**: Hex values ensure there cannot be collisions on case-insensitive systems (note IDs use both upper- and lowercase letters)
- **Efficient directory traversal**: Limits files per directory to 256, avoiding filesystem performance issues
- **Deterministic mapping**: Same note ID always maps to the same filesystem location

### Note representation

Each note folder contains exactly two files:

#### `meta.yaml`: Note metadata

Contains structured metadata about the note:

```yaml
id: "X6WplkgKJr5C"
type: "text"
mime: "text/html"
title: "My Note"
blob_id: "7XJSwh6apxkriWy2bX9P"
attributes:
  - "label1=value1"
  - "label2(inheritable)=value2"
  - "~relation1=5t6q5vF3hIx0"
children:
  - "yR0GpxGrUu6e|My prefix"
  - "ZCLwYMwtqjTu|"
```

Attribute and child branch IDs and positions are not explicitly stored. This approach is aligned with the "diff friendly" design goal.

#### Content file

- **Text notes**: `content.txt` (UTF-8 encoded)
- **Binary notes**: `content.bin` (raw bytes)

The content file type is determined by the note's `type` and `mime` type.

### Filesystem operations

The filesystem format supports bidirectional synchronization:

**Dump (Trilium → Filesystem)**
- Creates/updates note folders based on current Trilium state
- Compares content hashes to avoid unnecessary file writes
- Prunes stale folders from deleted notes

**Load (Filesystem → Trilium)**
- Recreates notes from filesystem representation
- Preserves all metadata (note fields, attributes, branches) and content
- Can target specific parent notes for orphaned subtrees
  - Otherwise, syncs notes "in-place" assuming they are already placed in the hierarchy

**Scan**
- Updates metadata when content files are modified externally
  - Otherwise content changes would not be propagated back to Trilium as content comparison is done based on hashes rather than raw data
- Useful after manual filesystem edits

This format enables version control integration, bulk editing, and external processing of notes while maintaining full fidelity with the original note structure.

## Example use cases

The following illustrates some common use cases, not covering all available options and functionality.

### Multi-instance configuration

Work with multiple Trilium instances using config files:

```bash
# check connection using specific instance from config
trilium-alchemy --instance my-private-notes --config-file my-config.yaml check
trilium-alchemy --instance my-public-notes --config-file my-config.yaml check
```

### Database backup/restore

Create database backups and restore from them:

```bash
# create backup-now.db
trilium-alchemy db backup

# create backup with auto-generated name from timestamp
trilium-alchemy db backup --auto-name

# create backup with specific name
trilium-alchemy db backup --name my-backup

# create backup and copy to specific location (requires TRILIUM_DATA_DIR or --data-dir)
trilium-alchemy db backup --dest /path/to/backup-now.db

# verify backup timestamp after creation (requires TRILIUM_DATA_DIR or --data-dir)
trilium-alchemy db backup --verify

# restore from backup (requires TRILIUM_DATA_DIR or --data-dir)
trilium-alchemy db restore /path/to/backup.db
```

### `.zip` export/import

Export and import note trees as `.zip` archives:

```bash
# export entire note tree
trilium-alchemy tree export /path/to/my-notes.zip

# export specific subtree by search
trilium-alchemy tree --search "#myProjectRoot" export /path/to/my-project-notes.zip

# import notes to root
trilium-alchemy tree import /path/to/my-notes.zip

# import subtree as child of specific note by search
trilium-alchemy tree --search "#myExtensions" import /path/to/my-extension.zip
```

### Template sync

As you develop templates, you may want to keep existing instances up to date. Attributes are inherited, but child notes are not updated when you update the template.

This command enables you to perform such re-synchronization of template instances with their templates:

```bash
# sync all template instances with their templates
trilium-alchemy note sync-template

# sync instances of specific template only
trilium-alchemy note sync-template --template-search "#template #task"
```

Template sync automatically:
- Adds new child notes from template to instances
- Recreates any cloning structure in the template
- Reorders child notes matched by title
- Preserves instance-specific modifications (places extra child notes at end)
- Works with both regular templates (`#template`) and workspace templates (`#workspaceTemplate`)

### Filesystem dump/load

Synchronize notes with filesystem representation as described above:

```bash
# dump entire note tree to filesystem
trilium-alchemy fs dump /path/to/fs-tree

# load filesystem dump back to Trilium
trilium-alchemy fs load /path/to/fs-tree

# dump subtree to filesystem
trilium-alchemy fs dump --search "#myCoolProject" /path/to/my-cool-project

# load subtree from filesystem and place as child of specific parent note
trilium-alchemy fs load --parent-search "#myProjects" /path/to/my-cool-project

# scan filesystem for content changes and update metadata
trilium-alchemy fs scan /path/to/fs-tree
```

## Usage

```{typer} trilium_alchemy.tools.cli.main:app
:prog: trilium-alchemy
:width: 80
:show-nested:
:make-sections:
```
