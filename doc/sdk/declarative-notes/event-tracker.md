(event-tracker)=
# Example: Event tracker

See `trilium-alchemy/example/event-tracker` for a fully featured showcase of both declarative and imperative approaches. An installation script is provided.

This provides a complete example of using declarative notes to design a note tree for event tracking with Trilium.

First, clone the repo and navigate to it:

```shell
git clone https://github.com/mm21/trilium-alchemy.git
cd trilium-alchemy/example/event-tracker
```

Then run its `__main__.py` to install it:

```shell
python -m event_tracker 
```

Exactly one note must be designated with label `#eventTrackerRoot` to be the hierarchy root.

```{warning}
This example is recommended to be installed in a non-production Trilium instance as it creates many notes.
```
