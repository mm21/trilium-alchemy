(event-tracker)=
# Event tracker

See `trilium-alchemy/example/event-tracker` for a fully featured showcase of both declarative and imperative approaches. An installation script is provided.

This provides a complete example of using declarative notes to design a note tree for event tracking with Trilium. It can be synchronized to a destination note identified by label `#lifeTrackerRoot`. Eventually sync functionality will be provided by a CLI.

First, clone the repo and navigate to it:

```shell
git clone https://github.com/mm21/trilium-alchemy.git
cd trilium-alchemy/example/event-tracker
```

Then run its `__main__`.py to install it:

```shell
python -m event_tracker 
````

A note must be designated with label `#eventTrackerRoot` to be the hierarchy root. Alternatively, you can pass `--root` to install it to your root note.

```{warning}
Any existing children the destination note will be deleted. Therefore you may want to install it in an empty subtree so as to not tamper with your existing notes.

In fact, especially at this stage, it's recommended to only run this example on a temporary Trilium instance, not your production instance.

To be safe, the installation script requires that you pass `--clobber` to delete existing children.
```