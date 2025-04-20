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
    host: http://localhost:8080
    token: MY_TOKEN

    # fully-qualified class name of root note for declarative push operation
    root_note_fqcn: my_notes.root.RootNote

# top-level data dir with subfolders per instance
root_data_dir:
  ./trilium/data
```

## Usage

```{typer} trilium_alchemy.tools.cli.main:app
:prog: trilium-alchemy
:width: 80
:show-nested:
:make-sections:
```
