def rollup(*mods: list):
    rollup_syms = []

    for mod in mods:
        try:
            all_ = mod.__all__
        except AttributeError as e:
            all_ = None

        try:
            rollup = mod.__rollup__
        except AttributeError as e:
            rollup = None

        try:
            nrollup = mod.__nrollup__
        except AttributeError as e:
            nrollup = None

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
