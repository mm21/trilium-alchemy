"""
Builds database to track physical and virtual canonical symbols.

Virtually canonical symbols: symbols exposed as the "canonical" public 
interface, but are not necessarily defined there in order to decouple 
implementation

Virtually aliased symbols: virtually canonical symbols imported from another 
module, e.g. in the containing package's __all__

Physically canonical symbols: defined in the module itself

Physically aliased symbols: imported from another module

Unless specified, "canonical" is assumed to mean "virtually canonical".
"""

from __future__ import annotations

# TODO: move out to separate package for reuse

from typing import Any
import dataclasses as dc
import inspect
import enum

import docutils
import sphinx
import myst_parser

from autodoc2.db import Database
from autodoc2.utils import ItemData

# eventually require user to import and provide
import trilium_alchemy

# only needed until module imported by root package
import trilium_alchemy.sync


class Symbol:
    """
    Represents a unique symbol, as captured by autodoc2. It may be defined
    in another module and imported, in which case it's considered
    "physically aliased".
    """

    symbol_map: SymbolMap

    # path to symbol as imported, e.g. trilium_alchemy.core.note.Note
    virt_path: str

    # physical path to symbol, e.g. trilium_alchemy.core._entity.note.note.Note
    phys_path: str

    # imported python object
    py_obj: Any

    # whether this is virtually canonical
    is_canonical: bool = False

    # if canonical, list of aliases
    aliases: list[Symbol] = None

    # if virtual alias, symbol this is an alias of
    canonical_symbol: Symbol = None

    def __init__(self, symbol_map: SymbolMap, path: str):
        self.symbol_map = symbol_map
        self.virt_path = path

        # TODO: handle error
        self.py_obj = eval(path)

        try:
            self.phys_path = f"{self.py_obj.__module__}.{self.py_obj.__name__}"
        except AttributeError as e:
            # is a module, so just use name
            self.phys_path = self.py_obj.__name__

        self._init()

        # add to map
        self.symbol_map.sym_map[path] = self

    def __repr__(self):
        py_obj = f"\n  py_obj: {self.py_obj}"
        is_canonical = f"\n  is_canonical: {self.is_canonical}"

        if self.is_canonical:
            canonical = ""
            aliases_ = ", ".join([sym.virt_path for sym in self.aliases])
            aliases = f"\n  aliases: {aliases_}"
        else:
            if self.canonical_symbol:
                canonical_name = self.canonical_symbol.virt_path
            else:
                canonical_name = "None"
            canonical = f"\n  canonical: {canonical_name}"
            aliases = ""

        return f"\nSymbol {self.virt_path}{py_obj}{is_canonical}{canonical}{aliases}"

    def _init(self):
        """additional init if required by subclass"""

    @property
    def name(self) -> str:
        return self.virt_path.split(".")[-1]

    def set_canonical(self):
        """
        Set this symbol as a canonical symbol.
        """
        assert self.py_obj not in self.symbol_map.obj_map

        self.is_canonical = True
        self.aliases = []
        self.symbol_map.obj_map[self.py_obj] = self

    def check_canonical(self):
        """
        Check if this symbol should be considered canonical.
        """
        if self.is_alias:
            if self.virt_path == self.phys_path:
                self.set_canonical()

    def check_alias(self):
        """
        Check if this symbol has a canonical symbol.
        """
        if self.is_alias:
            if self.py_obj in self.symbol_map.obj_map:
                # there's a canonical symbol for this object
                self.canonical_symbol = self.symbol_map.obj_map[self.py_obj]
                self.canonical_symbol.aliases.append(self)

    def _get_attr_impl(self, cls, attr):
        """
        Get the provided attribute value from class along with the class
        from which it's inherited.

        Can't naively use getattr(cls, attr) since it may activate
        a descriptor. Manually traverse MRO and check vars() for each class.

        Also accounts for renamed declarative attributes. For example:

        class MyNote(Note):
            title = 'My title'

        Here the attribute of interest for documentation is actually "title_"
        since it gets renamed by the metaclass to keep the "title" descriptor
        intact.
        """

        # raise AttributeError if it couldn't be found since None is a valid
        # attribute value
        def get_attr(cls, attr):
            attrs = vars(cls)

            if attr in attrs:
                # has attribute
                key = attr
            elif f"{attr}_" in attrs:
                # has renamed declarative attribute (e.g. title -> title_)
                key = f"{attr}_"
            else:
                raise AttributeError

            return (attrs[key], cls)

        for ancestor in cls.mro():
            try:
                return get_attr(ancestor, attr)
            except AttributeError:
                pass

    def _get_attr(self, cls, attr):
        return self._get_attr_impl(cls, attr)[0]

    def get_ancestor(self, attr):
        cls = self._get_attr_impl(self.py_obj, attr)[1]
        return f"{cls.__module__}.{cls.__name__}"

    def get_attr_value(self, attr: str):
        value = self._get_attr(self.py_obj, attr)

        # don't need to show value for enums
        if type(self.py_obj) is enum.EnumMeta:
            return None

        # add markup to value based on its type

        # try to lookup symbol
        if value in self.symbol_map.obj_map:
            py_obj = value
            descriptor = False
        elif type(value) in self.symbol_map.obj_map:
            # descriptor
            py_obj = type(value)
            descriptor = True
        else:
            py_obj = None

        if py_obj:
            # have an internal symbol, so add a reference
            symbol = self.symbol_map.obj_map[py_obj]

            if descriptor:
                # include parentheses for clarity
                name = f"{symbol.name}()"
            else:
                name = symbol.name

            return f"{{obj}}`{name} <{symbol.virt_path}>`"
        elif isinstance(value, str):
            # string, need to add quotes
            return f'`"{value}"`{{l=python}}'
        elif (
            value is None or isinstance(value, int) or isinstance(value, float)
        ):
            # common python types
            # TODO: add more?
            return f"`{value}`{{l=python}}"

        print(
            f"Warning: got a value for {self.virt_path}.{attr} with unknown type: {value}"
        )
        return f"`{type(value).__name__}`"

    @property
    def is_alias(self):
        return not self.is_canonical

    @property
    def is_phys_canonical(self):
        return self.virt_path == self.phys_path

    @property
    def is_phys_alias(self):
        return not self.is_phys_canonical

    @property
    def db_item(self) -> ItemData:
        if self.is_canonical or self.canonical_symbol is None:
            return self.symbol_map.db.get_item(self.virt_path)
        else:
            # assert self.canonical_symbol is not None
            return self.symbol_map.db.get_item(self.canonical_symbol.virt_path)

    @property
    def canonical(self) -> Symbol:
        if self.is_canonical or self.canonical_symbol is None:
            return self
        else:
            return self.canonical_symbol


class Module(Symbol):
    all_: list[str]
    """__all__ retrieved from importing module"""

    symbols: list[Symbol]
    """symbols from __canonical_syms__"""

    children: list[Module]
    """child modules from __canonical_children__"""

    def __repr__(self):
        symbols = ", ".join([sym.virt_path for sym in self.symbols])
        symbols_line = f"  symbols: {symbols}"
        children = ", ".join([mod.virt_path for mod in self.children])
        children_line = f"  children: {children}"
        return super().__repr__() + f"\n{symbols_line}\n{children_line}"

    def _init(self):
        self.symbols = []  # public symbols from __all__
        self.children = []  # public submodules

        # get symbol lists
        try:
            all_ = self.py_obj.__all__
        except AttributeError as e:
            # mod didn't define __all__
            all_ = []

        try:
            canonical_syms = self.py_obj.__canonical_syms__
        except AttributeError as e:
            canonical_syms = []

        try:
            canonical_children = self.py_obj.__canonical_children__
        except AttributeError as e:
            canonical_children = []

        # create symbols
        for sym in all_:
            sym_path = f"{self.virt_path}.{sym}"

            symbol = Symbol(self.symbol_map, sym_path)
            if sym in canonical_syms:
                symbol.set_canonical()
            self.symbols.append(symbol)

        assert set(canonical_syms) <= set(
            all_
        ), "__canonical_syms__ must be subset of __all__"

        # recurse into children
        for mod in canonical_children:
            mod_path = f"{self.virt_path}.{mod}"

            module = Module(self.symbol_map, mod_path)
            module.set_canonical()
            self.children.append(module)

        # autodoc2 needs child modules present in all to recurse into them
        self.all_autodoc2 = all_ + canonical_children

    @property
    def canonical_symbols(self):
        """list of virtually canonical symbols in this module"""
        return [sym for sym in self.symbols if sym.is_canonical]

    @property
    def alias_symbols(self):
        """list of virtually alias symbols in this module"""
        return [sym for sym in self.symbols if sym.is_alias]


class SymbolMap:
    """
    Maintain symbols found by traversing autodoc2's database and introspection.
    """

    # database object
    db: Database

    # top-level package
    root_module: Module

    # top-level package name
    root_path: str

    # mapping of path -> symbol
    sym_map: dict[str, Symbol]

    # mapping of obj -> canonical symbol
    obj_map: dict[Any, Symbol]

    def __init__(self, root_path: str):
        self.root_path = root_path
        self.sym_map = dict()
        self.obj_map = dict()

    @property
    def canonical_map(self) -> dict[str, Symbol]:
        return {
            path: sym for path, sym in self.sym_map.items() if sym.is_canonical
        }

    @property
    def phys_map(self) -> dict[str, Symbol]:
        """
        Return mapping indexed by physical path, e.g.
        trilium_alchemy.core._entity.note.note.Note.
        """
        return {sym.phys_path: sym for path, sym in self.sym_map.items()}

    # TODO: warning about unclassified symbols
    # - unable to determine canonical vs alias
    # - assume canonical if not imported elsewhere
    def build(self, db: Database):
        self.db = db

        # recursively traverse modules to find canonical symbols
        self.root_module = Module(self, self.root_path)

        # if not specified, default to physically canonical symbols
        for path, symbol in self.sym_map.items():
            symbol.check_canonical()

        # set reference to canonical symbol for aliases
        for path, symbol in self.sym_map.items():
            # check if there's a registered canonical symbol
            symbol.check_alias()

        print(f"Top map:")
        for path, sym in self.sym_map.items():
            print(f"{path} -> {sym.py_obj}")

        print(f"Symbol map:")
        for py_obj, sym in self.obj_map.items():
            print(f"{py_obj} -> {sym.virt_path}")

        # clear refs to modules since they can't be pickled
        self._cleanup_modules()

    def _cleanup_modules(self):
        for path, symbol in self.sym_map.items():
            if inspect.ismodule(symbol.py_obj):
                if symbol.py_obj in self.obj_map:
                    del self.obj_map[symbol.py_obj]
                symbol.py_obj = None

    def lookup(self, name: str) -> Symbol | None:
        """
        Try to find symbol with provided name in database.
        It may be the name of a symbol with no modpath.
        """

        if "." in name:
            if name.startswith(self.root_path):
                full_name = name
            else:
                return None
        else:
            full_name = f"{self.root_path}.{name}"

        # try virtual path first
        symbol = self.sym_map.get(full_name, None)

        if symbol is None:
            # try physical path
            symbol = self.phys_map.get(full_name, None)

            if symbol is None:
                # eval obj and try physical path

                try:
                    py_obj = eval(full_name)
                except (AttributeError, SyntaxError, NameError) as e:
                    py_obj = None

                if py_obj:
                    if py_obj in self.obj_map:
                        return self.obj_map[py_obj]

        return symbol

    def resolve(self, name: str) -> str:
        """
        Get canonical name if it exists, otherwise return name.
        """
        if symbol := self.lookup(name):
            # internal symbol, get canonical name
            return symbol.canonical.virt_path
        else:
            # external symbol, e.g. Exception
            return name


class Env:
    root_path: str
    symbol_map: SymbolMap

    def __init__(self, root_path: str):
        self.root_path = root_path
        self.symbol_map = SymbolMap(root_path)

    def db_fixup(self, db: Database):
        """
        Use db_fixup hook to populate 'all' for modules and create alias
        mappings.
        """

        self.db = db

        self.symbol_map.build(db)

        self.set_ref()
        self.set_all()
        self.map_canonical()
        self.update_doc()

    def set_ref(self):
        """
        Set reference to Symbol object in autodoc2's item so we can access
        it later as needed.
        """
        for full_name, item in self.db._items.items():
            if symbol := self.symbol_map.sym_map.get(full_name, None):
                item["symbol_obj"] = symbol

    def set_all(self):
        """
        Set "all" from symbol_map. Required since dynamic __all__ can't be
        captured by static analysis.
        """
        for full_name, item in self.db._items.items():
            symbol = item.get("symbol_obj", None)

            # set all for package or module
            if item["type"] in {"package", "module"}:
                if symbol:
                    all_ = symbol.all_autodoc2
                else:
                    all_ = []

                item["all"] = all_

                if len(all_):
                    print(f"Set all for {full_name}: {all_}")

    def map_canonical(self):
        """
        Rename physically canonical symbols to virtual canonical paths.

        Example:
            trilium_alchemy.core.note.note.Note ->
            trilium_alchemy.core.note.Note
        """

        def recurse(db: Database, item: ItemData, path_from: str, path_to: str):
            # recurse into children first

            for child_item in list(self.db.get_children(path_from)):
                short_name = child_item["full_name"].split(".")[-1]
                child_to = f"{path_to}.{short_name}"

                recurse(db, child_item, child_item["full_name"], child_to)

            # rename this item
            item["full_name"] = path_to
            assert path_to not in db._items
            assert path_from in db._items
            db._items[path_to] = db._items[path_from]
            del db._items[path_from]

        # traverse all canonical symbols
        for py_obj, symbol in self.symbol_map.obj_map.copy().items():
            if (
                symbol.phys_path in self.db._items
                and symbol.phys_path != symbol.virt_path
            ):
                # found a symbol which needs to be mapped to its virtual path
                recurse(
                    self.db,
                    self.db.get_item(symbol.phys_path),
                    symbol.phys_path,
                    symbol.virt_path,
                )

    def update_doc(self):
        """
        Append decorator descriptions to docstring.
        """
        for full_name, item in self.db._items.items():
            if "symbol_obj" in item:
                symbol = item["symbol_obj"]

                if hasattr(symbol.py_obj, "_decorator_doc"):
                    if len(symbol.py_obj._decorator_doc):
                        doc = "\n".join(symbol.py_obj._decorator_doc)
                        item["doc"] += f"\n\n*Added by decorators:*\n\n" + doc

    def doctree_read(self, app, doctree):
        self.resolve_refs(app, doctree)
        self.cleanup_params(app, doctree)
        self.expand_titles(app, doctree)

    def _shorten_pending_xref(self, pending_xref: sphinx.addnodes.pending_xref):
        text = pending_xref.astext()

        # only shorten internal refs
        if text.startswith(self.root_path):
            short_name = text.split(".")[-1]
            self._update_text(pending_xref, short_name)

    def _update_text(
        self,
        node: docutils.nodes.Node,
        new_text: str,
        parent: docutils.nodes.Node = None,
    ):
        text = node.next_node(condition=docutils.nodes.Text)
        assert text is not None

        text.parent.replace(text, docutils.nodes.Text(new_text))

    def _resolve_item(self, name: str) -> tuple[ItemData | None, Symbol | None]:
        """
        Try to get item given its name, which may not include
        a modpath.

        If there's a corresponding Symbol, it's returned as well. The
        Symbol may be the containing class - members of classes don't
        have an entry in the SymbolMap.
        """

        # try to resolve as symbol
        symbol = self.symbol_map.lookup(name)

        if symbol is None:
            if "." not in name:
                return

            # try as Class.member
            cls_name, member_name = name.rsplit(".", maxsplit=1)

            symbol = self.symbol_map.lookup(cls_name)
            if symbol is None:
                return

            full_name = f"{symbol.canonical.virt_path}.{member_name}"
        else:
            full_name = symbol.canonical.virt_path

        return (self.symbol_map.db.get_item(full_name), symbol.canonical)

    def _resolve_ref(self, pending_xref: sphinx.addnodes.pending_xref):
        """
        Resolve reference to top-level symbol (e.g. trilium_alchemy.*).
        """

        target = pending_xref.get("reftarget", None)

        if target is None:
            return

        result = self._resolve_item(target)

        if result is None:
            return

        item, symbol = result

        if symbol is None or item is None:
            print(f"Warning: failed to get item and/or symbol for {target}")
            return

        full_name = item["full_name"]
        type_ = item["type"]

        # set target
        pending_xref["reftarget"] = full_name

    def resolve_refs(self, app, doctree):
        for pending_xref in doctree.traverse(
            condition=sphinx.addnodes.pending_xref
        ):
            self._resolve_ref(pending_xref)

    def _get_parent(self, node, cls):
        parent = node.parent
        while parent is not None:
            if isinstance(parent, cls):
                return parent
            parent = parent.parent

    def _get_parameter(
        self,
        parameterlist: sphinx.addnodes.desc_parameterlist,
        name: sphinx.addnodes.literal_strong,
    ) -> sphinx.addnodes.desc_parameter:
        for parameter in parameterlist.children:
            if parameter.children[0].astext() == name.astext():
                return parameter

    def _insert_xref(self, inline: docutils.nodes.inline):
        """
        Insert pending_xref in place. Used for param defaults.
        """

        assert (
            len(inline.children) == 1
        ), f"Multiple children of default: {inline.astext()}"

        default = inline.children[0]

        # only handle basic defaults for now
        if default.astext() in {"None", "True", "False"}:
            # create xref node
            xref = sphinx.addnodes.pending_xref()

            xref["reftarget"] = default.astext()
            xref["refdomain"] = "py"
            xref["refspecific"] = "False"
            xref["reftype"] = "any"

            # move default text to xref node
            inline.remove(default)

            xref += default
            inline += xref

    def _lookup_func(self, doctree, full_name):
        for signature in doctree.traverse(
            condition=sphinx.addnodes.desc_signature
        ):
            if signature["ids"][0] == full_name:
                parameterlist = signature.next_node(
                    condition=sphinx.addnodes.desc_parameterlist
                )

                returns = signature.next_node(
                    condition=sphinx.addnodes.desc_returns
                )

                assert parameterlist is not None

                return (parameterlist, returns)

        raise Exception(f"Failed to find parameterlist for: {full_name}")

    def cleanup_params(self, app, doctree):
        """
        Performs parameter cleanups and improvements:

        - Add refs to param defaults

        - Extract types from parameterlist, returns to field_list
            This is done by sphinx-autodoc-typehints, but only works for
            autodoc, not autodoc2.

        - Convert params in field_list from bullet list to definition list
            This looks nicer since the descriptions all start from consistent
            horizontal offsets on the screen.
            Also normalizes to a list - functions with only one param result
            in a paragraph rather bullet list.
        """

        def process_parameterlist(
            field_body: docutils.nodes.field_body,
            parameterlist: sphinx.addnodes.desc_parameterlist,
        ):
            def process_paragraph(
                paragraph: docutils.nodes.paragraph,
                def_list: docutils.nodes.definition_list,
                parameterlist: sphinx.addnodes.desc_parameterlist,
            ):
                """
                Functions with only one arg get added as a paragraph rather
                than bullet list. It has the same structure as the paragraph
                in the list_item of a bullet list, so use the same approach
                for both.
                """

                def process_term(
                    term: docutils.nodes.term,
                    parameter: sphinx.addnodes.desc_parameter,
                ):
                    literal = sphinx.addnodes.literal_strong()
                    literal += docutils.nodes.Text(": ")

                    term += literal

                    desc_sig_name = parameter.children[3]

                    # copy param type hints
                    for annotation_node in desc_sig_name.children:
                        term += annotation_node.deepcopy()

                    # copy defaults
                    if len(parameter.children) > 7:
                        default: docutils.nodes.inline = parameter.children[7]

                        literal = sphinx.addnodes.literal_strong()
                        literal += docutils.nodes.Text(" = ")
                        literal += default.deepcopy()

                        term += literal

                # should be 3 children of paragraph:
                # - formatted arg name (literal_strong)
                # - " - " (ignore)
                # - arg description
                assert len(paragraph.children) == 3
                name, dash, desc = paragraph.children

                desc_p = docutils.nodes.paragraph()
                desc_p += desc

                # create definition list item
                def_list_item = docutils.nodes.definition_list_item()

                # add children as term, definition

                term = docutils.nodes.term()
                definition = docutils.nodes.definition()

                term += name
                definition += desc_p

                def_list_item += term
                def_list_item += definition

                def_list += def_list_item

                # get corresponding parameter
                parameter = self._get_parameter(parameterlist, name)

                # kwargs doesn't have a corresponding parameter
                if parameter:
                    # add type info to term
                    process_term(term, parameter)

            def process_bullet_list(
                bullet_list: docutils.nodes.bullet_list,
                def_list: docutils.nodes.definition_list,
            ):
                """
                Functions with multiple args get added as bullet lists.
                """

                # traverse children of bullet list and convert to
                # definition list
                for list_item in list(bullet_list.children):
                    # bullet_list child should be a list item with exactly
                    # 1 child (a paragraph)
                    assert isinstance(list_item, docutils.nodes.list_item)

                    paragraph = list_item.children[0]
                    assert isinstance(paragraph, docutils.nodes.paragraph)

                    process_paragraph(paragraph, def_list, parameterlist)

            assert len(field_body.children) == 1
            list_node = field_body.children[0]

            # create definition list to hold new arg list
            def_list = docutils.nodes.definition_list()

            if isinstance(list_node, docutils.nodes.bullet_list):
                # multiple params
                process_bullet_list(list_node, def_list)
            elif isinstance(list_node, docutils.nodes.paragraph):
                # single param
                process_paragraph(list_node, def_list, parameterlist)
            elif isinstance(list_node, docutils.nodes.definition_list):
                # already what we want
                return
            else:
                print(
                    f"Warning: unknown list_node: {type(list_node)}, {list_node}"
                )
                return

            # replace original list with definition list
            field_body.replace(list_node, def_list)

        def process_returns(
            field_body: docutils.nodes.field_body,
            returns: sphinx.addnodes.desc_returns,
        ):
            # insert copy of returns as first child of field_body
            paragraph = docutils.nodes.paragraph()

            for child in returns.children:
                paragraph += child.deepcopy()

            field_body.insert(0, paragraph)

        def process_field_list(
            field_list: docutils.nodes.field_list,
            parameterlist: sphinx.addnodes.desc_parameterlist,
            returns: sphinx.addnodes.desc_returns,
        ):
            """
            field_list can have both parameters and returns.
            Find out which this has and invoke the right functions.
            """

            for field in field_list.traverse(condition=docutils.nodes.field):
                field_name, field_body = field.children

                assert isinstance(field_name, docutils.nodes.field_name)
                assert isinstance(field_body, docutils.nodes.field_body)

                name = field_name.astext()

                if name == "Parameters":
                    process_parameterlist(field_body, parameterlist)
                elif name == "Returns":
                    process_returns(field_body, returns)
                # TODO: handle "Raises"?

        def process_func(desc: sphinx.addnodes.desc, full_name: str):
            field_list = desc.next_node(condition=docutils.nodes.field_list)

            if field_list is not None:
                parameterlist, returns = self._lookup_func(doctree, full_name)

                process_field_list(field_list, parameterlist, returns)

        def process_class(desc: sphinx.addnodes.desc, full_name: str):
            # check if class has constructor
            init = self.symbol_map.db.get_item(f"{full_name}.__init__")

            if init:
                # has init, so process as func
                field_list = desc.next_node(condition=docutils.nodes.field_list)

                if field_list:
                    # also get parameterlist
                    parameterlist = desc.next_node(
                        condition=sphinx.addnodes.desc_parameterlist
                    )
                    assert parameterlist is not None

                    # __init__ can't have returns
                    process_field_list(field_list, parameterlist, None)

        # traverse parameters
        for parameter in doctree.traverse(
            condition=sphinx.addnodes.desc_parameter
        ):
            # shorten xrefs
            for pending_xref in parameter.traverse(
                condition=sphinx.addnodes.pending_xref
            ):
                self._shorten_pending_xref(pending_xref)

            # insert xref in param default
            # TODO: helper to traverse for inline with classes="default_value"
            if len(parameter.children) > 7:
                default: docutils.nodes.inline = parameter.children[7]
                self._insert_xref(default)

        # traverse returns
        for returns in doctree.traverse(condition=sphinx.addnodes.desc_returns):
            # shorten xrefs
            for pending_xref in returns.traverse(
                condition=sphinx.addnodes.pending_xref
            ):
                self._shorten_pending_xref(pending_xref)

        # traverse signatures
        for signatures in doctree.traverse(
            condition=sphinx.addnodes.desc_signature
        ):
            # shorten xrefs
            for pending_xref in signatures.traverse(
                condition=sphinx.addnodes.pending_xref
            ):
                self._shorten_pending_xref(pending_xref)

        # traverse desc objects
        for desc in doctree.traverse(condition=sphinx.addnodes.desc):
            domain = desc["domain"]
            obj_type = desc["objtype"]

            signature = desc.children[0]

            full_name = signature["ids"][0]

            if obj_type == "class":
                process_class(desc, full_name)
            elif obj_type in {"method", "function"}:
                process_func(desc, full_name)

    def expand_titles(self, app, doctree):
        """
        The sidebar navigation loses its monospace font when a custom
        title is provided to shorten the module names. Alternatively a short
        name can be set for the title of the page itself, but it's better to
        see the full modpath as the title when viewing the page.

        The solution to enable short module names in the sidebar while having
        the full modpath for the title is to use the short name for the title,
        but expand it here to the full name. The shortened title in the sidebar
        will remain intact.
        """

        for section in doctree.traverse(condition=docutils.nodes.section):
            if len(section.children) < 2:
                continue

            # should be a section with title and index as children
            title, index = section.children[0:2]

            if not isinstance(index, sphinx.addnodes.index):
                continue

            if not len(title.children) == 1:
                continue

            literal = title.children[0]

            if not isinstance(literal, docutils.nodes.literal):
                continue

            entries = index["entries"]

            mod_spec = entries[0][2]

            # should be module-(name)
            mod_full = mod_spec.split("-")[1]

            text = literal.children[0]
            literal.replace(text, docutils.nodes.Text(mod_full))
