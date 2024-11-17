"""
Entry point of `trilium-alchemy` CLI.

Planned commands:

- `extensions`
    - Manage extensions: List currently installed, install/uninstall/upgrade 
    from path or git repo
        - User-defined destination note for extensions given by 
        `#extensionsRoot` label
- `resync`
    - Re-sync notes with a given template, useful to apply template changes
    to existing notes with that template
- `export`/`import`
    - Export/import (zip file by default)
    - Custom exporter/importer:
        - `export --exporter my_pkg.my_exporter path/to/destination`
- `backup`
    - Create backup in provided path
- `test`
    - Run sanity tests for ETAPI functionality
    - Run stress tests: generate hierarchy with many notes to stress test
    both Trilium itself and TriliumAlchemy
"""
