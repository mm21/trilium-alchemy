# CLI

CLI to manage Trilium by exposing SDK functionality.

## Configuration

The tool can be configured via any of the following, in order of precedence:

- `.yaml` file
  - Supports multiple Trilium instances
- Command-line options
- Environment variables
- `.env` file

### `.yaml` file example

```yaml
# mapping of instance names to info
instances:
  my-notes:
    # connection info, either "token" or "password" required
    host: "http://localhost:8080"
    token: "MY_TOKEN"
    password: "MY_PASSWORD"

    # optional fully-qualified class name of root note for tree push
    root_note_fqcn: "my_notes.root.RootNote"

    # optional data dir which overrides root_data_dir
    data_dir: "./trilium_data/my-notes"

# top-level data dir with subfolders per instance
root_data_dir:
  "./trilium_data"
```

## Usage

```{typer} trilium_alchemy.tools.cli.main:app
:prog: trilium-alchemy
:width: 80
:show-nested:
:make-sections:
```
