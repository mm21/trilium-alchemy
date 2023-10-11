"""
This is a mechanism to aggregate ("roll-up") symbols from packages to their
containing packages.

A package has some control over which symbols are rolled up:

- To only roll up specific symbols, define `__rollup__`; this is the allow-list
    - If not defined, symbols in `__all__` are rolled up
- To omit specific symbols, define `__nrollup__`; this is the block-list

```todo
Move this to a separate package and add dependency
```
"""

from types import ModuleType


def rollup(*mods: ModuleType) -> list[str]:
    rollup_syms = []

    for mod in mods:
        all_: list[str] | None = None
        rollup: list[str] | None = None
        nrollup: list[str] | None = None

        allow_list: list[str]
        block_list: list[str]

        try:
            all_ = mod.__all__
        except AttributeError as e:
            pass

        try:
            rollup = mod.__rollup__
        except AttributeError as e:
            pass

        try:
            nrollup = mod.__nrollup__
        except AttributeError as e:
            pass

        if rollup is not None:
            allow_list = rollup
        elif all_ is not None:
            allow_list = all_
        else:
            allow_list = []

        if nrollup is not None:
            block_list = nrollup
        else:
            block_list = []

        rollup_syms += [sym for sym in allow_list if sym not in block_list]

    return rollup_syms
