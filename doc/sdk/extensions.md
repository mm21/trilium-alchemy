# Trilium extensions

A number of helper classes are provided for facilitating development of extensions. See {obj}`trilium_alchemy.lib.extension_types` for a full list.

For example, to create a template called `Task`:

```python
class Task(BaseTemplateNote):
    icon = "bx bx-task"
```

This is equivalent to:

```python
@label("template")
@label("iconClass", "bx bx-task")
class Task(BaseDeclarativeNote):
    pass
```
