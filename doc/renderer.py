"""Renderer for MyST."""
from __future__ import annotations

import re
import typing as t

from autodoc2.render.base import RendererBase
from autodoc2.utils import ItemData
from conf import package
from util import Module, Symbol

_RE_DELIMS = re.compile(r"(\s*[\[\]\(\),]\s*)")


class MystRenderer(RendererBase):
    """Render the documentation as MyST."""

    EXTENSION = ".md"

    _symbol_map = None

    @property
    def symbol_map(self):
        if self._symbol_map is None:
            # just use package name as a known symbol which should exist
            item = self.get_item(package)

            if item is None:
                raise ValueError(f"Root item {package} does not exist")

            symbol = item["symbol_obj"]
            self._symbol_map = symbol.symbol_map

        return self._symbol_map

    def render_item(self, full_name: str, **kwargs) -> t.Iterable[str]:
        item = self.get_item(full_name)

        if full_name in self.symbol_map.sym_map:
            symbol = self.symbol_map.sym_map[full_name]
        else:
            symbol = None

            # only proceed for symbols not expected to exist in symbol db,
            # i.e. members of classes
            if item["type"] in {"package", "module"}:
                yield ":orphan:"
                return

        type_ = item["type"]

        type_map = {
            "package": self.render_package,
            "module": self.render_module,
            "function": self.render_function,
            "class": self.render_class,
            "exception": self.render_exception,
            "property": self.render_property,
            "method": self.render_method,
            "attribute": self.render_attribute,
            "data": self.render_data,
        }

        assert type_ in type_map

        yield from type_map[type_](item, symbol, **kwargs)

    def generate_summary(
        self,
        symbols: list[Symbol],
        name_map: dict[str, str] | None = None,
        canonical: bool = False,
        mod_parent: str | None = None,  # only applies if not canonical
    ) -> t.Iterable[str]:
        name_map = name_map or {}
        yield "````{list-table}"
        yield ":class: autosummary longtable"
        yield ":align: left"
        yield ""
        for symbol in symbols:
            # TODO get signature (for functions, etc), plus sphinx also runs rst.escape

            full_name = symbol.canonical.virt_path
            name = name_map[full_name] if full_name in name_map else full_name

            yield f"* - {{py:obj}}`{name} <{full_name}>`"

            if not canonical:
                mod_from = symbol.canonical.virt_path.rsplit(".", maxsplit=1)[0]
                mod_from_short = mod_from.replace(f"{mod_parent}.", "")

                yield f"  - {{py:obj}}`{mod_from_short} <{mod_from}>`"

            yield from self.render_docstring(symbol.db_item, summary=True)

        yield "````"

    @staticmethod
    def enclosing_backticks(text: str) -> str:
        """Ensure the enclosing backticks are more than any inner ones."""
        backticks = "```"
        while backticks in text:
            backticks += "`"
        return backticks

    def render_module(
        self, item: ItemData, module: Module, **kwargs
    ) -> t.Iterable[str]:
        """Create the content for a module."""

        if self.standalone and self.is_hidden(item):
            yield from ["---", "orphan: true", "---", ""]

        full_name = item["full_name"]
        short_name = full_name.split(".")[-1]

        # will change it to the full name later, but short name still applies
        # to table of contents
        yield f"({full_name})="
        yield f"# `{short_name}`"

        yield ""

        yield f"```{{py:module}} {full_name}"
        if self.no_index(item):
            yield ":noindex:"
        if self.is_module_deprecated(item):
            yield ":deprecated:"
        yield from ["```", ""]

        yield from self.render_docstring(item, allow_titles=True)

        visible_children = [child.virt_path for child in module.children]

        if visible_children:
            yield from [
                "```{toctree}",
                ":hidden:",
                "",
            ]
            yield from visible_children
            yield "```"
            yield ""

        if self.show_module_summary(item):
            for heading, types in [
                ("Class index", {"class"}),
                ("Function index", {"function"}),
                ("Data index", {"data"}),
                ("Exception index", {"exception"}),
                ("External index", {"external"}),
            ]:
                index_symbols = [
                    symbol
                    for symbol in module.symbols
                    if symbol.db_item["type"] in types
                ]

                if index_symbols:
                    yield from [f"### {heading}", ""]

                    for category, canonical in [
                        ("Canonical", True),
                        ("Imported", False),
                    ]:
                        index_filtered = [
                            sym
                            for sym in index_symbols
                            if sym.is_canonical is canonical
                        ]

                        if index_filtered:
                            yield from [
                                f":::symbol-category",
                                f"```{{rubric}} {category}",
                                "```",
                                ":::",
                                "",
                            ]

                            yield from self.generate_summary(
                                index_filtered,
                                name_map={
                                    sym.canonical.virt_path: sym.virt_path.split(
                                        "."
                                    )[
                                        -1
                                    ]
                                    for sym in index_filtered
                                },
                                canonical=canonical,
                                mod_parent=full_name,
                            )
                            yield ""

        canonical_symbols = [
            symbol.virt_path for symbol in module.symbols if symbol.is_canonical
        ]

        if len(canonical_symbols):
            yield from ["### Symbols", ""]
            for full_name in canonical_symbols:
                yield from self.render_item(full_name)

    def render_package(
        self, item: ItemData, module: Module, **kwargs
    ) -> t.Iterable[str]:
        """Create the content for a package."""
        yield from self.render_module(item, module)

    def render_function(
        self, item: ItemData, symbol: Symbol, **kwargs
    ) -> t.Iterable[str]:
        """Create the content for a function."""
        short_name = item["full_name"].split(".")[-1]
        show_annotations = self.show_annotations(item)
        sig = (
            f"{short_name}({self.format_args(item['args'], show_annotations)})"
        )
        if show_annotations and item.get("return_annotation"):
            sig += f" -> {self.format_annotation(item['return_annotation'])}"

        yield f"````{{py:function}} {sig}"
        yield f":canonical: {item['full_name']}"
        if self.no_index(item):
            yield ":noindex:"
        # TODO overloads
        if "async" in item.get("properties", []):
            yield ":async:"
            # TODO it would also be good to highlight if singledispatch decorated,
            # or, more broadly speaking, decorated at all
        yield ""

        yield from self.render_info(item=item, symbol=symbol, **kwargs)

        yield "````"
        yield ""

    def render_exception(
        self, item: ItemData, symbol: Symbol, **kwargs
    ) -> t.Iterable[str]:
        """Create the content for an exception."""
        yield from self.render_class(item, symbol)

    def _check_subclass(self, item: ItemData, cls_name: str):
        """
        Check if provided class is a subclass of provided class name.
        """
        is_subclass = False
        bases = self.get_bases(item)
        if cls_name in bases:
            is_subclass = True
        else:
            subclasses = []
            for base in bases:
                item = self.get_item(base)
                if item:
                    subclasses.append(item)
            return any(
                self._check_subclass(subclass, cls_name)
                for subclass in subclasses
            )

        return is_subclass

    def render_class(
        self, item: ItemData, symbol: Symbol, **kwargs
    ) -> t.Iterable[str]:
        """Create the content for a class."""

        # check if sig should be skipped
        # TODO: make generic, config-based (register callback?)
        mixin_subclass = (
            item["full_name"]
            != "trilium_alchemy.core.declarative.base.BaseDeclarativeNote"
        ) and self._check_subclass(
            item, "trilium_alchemy.core.declarative.base.BaseDeclarativeMixin"
        )
        skip_constructor = mixin_subclass
        skip_inherited = mixin_subclass

        # ancestors to skip
        ancestors_skip = {
            "trilium_alchemy.core.entity.BaseEntity",
            "trilium_alchemy.core.note.Note",
            "trilium_alchemy.core.declarative.base.BaseDeclarativeNote",
            "trilium_alchemy.core.declarative.base.BaseDeclarativeMixin",
            "collections.abc.Mapping",
            "collections.abc.MutableMapping",
        }

        # members to skip
        members_skip = {
            "init",
        }

        short_name = item["full_name"].split(".")[-1]
        constructor = self.get_item(f"{item['full_name']}.__init__")
        sig = short_name
        if constructor and "args" in constructor and not skip_constructor:
            args = self.format_args(
                constructor["args"],
                self.show_annotations(item),
                ignore_self="self",
            )
            sig += f"({args})"

        # note, here we can cannot yield by line,
        # because we need to look ahead to know the length of the backticks

        lines: list[str] = [f":canonical: {item['full_name']}"]
        if self.no_index(item):
            lines += [":noindex:"]
        lines += [""]

        if self.config.class_docstring == "merge" and not skip_constructor:
            lines += self.render_init(item)

        lines += self.render_bases(item)
        lines += self.render_info(item=item, symbol=symbol, **kwargs)

        groups = [
            "attribute",
            "property",
            "method",
            "class",
        ]

        for group in groups:
            for child in self.get_children(item, {group}):
                child_name = child["full_name"]

                if child_name.endswith(".__init__") and (
                    self.config.class_docstring == "merge" or skip_constructor
                ):
                    continue

                # skip some inherited members to cleanup Note subclasses
                if skip_inherited:
                    child_short_name = child_name.split(".")[-1]

                    if child_short_name in members_skip:
                        # skip member
                        continue
                    else:
                        # check if member is provided by an ancestor
                        ancestor = symbol.get_ancestor(child_short_name)

                        if ancestor_sym := self.symbol_map.lookup(ancestor):
                            ancestor = ancestor_sym.canonical.virt_path

                        if ancestor in ancestors_skip:
                            continue

                for line in self.render_item(child_name, parent=symbol):
                    lines.append(line)

        backticks = self.enclosing_backticks("\n".join(lines))
        yield f"{backticks}{{py:{item['type']}}} {sig}"
        for line in lines:
            yield line
        yield backticks
        yield ""

    def render_property(
        self, item: ItemData, symbol: Symbol, **kwargs
    ) -> t.Iterable[str]:
        """Create the content for a property."""
        short_name = item["full_name"].split(".")[-1]
        yield f"````{{py:property}} {short_name}"
        yield f":canonical: {item['full_name']}"
        if self.no_index(item):
            yield ":noindex:"
        for prop in ("abstractmethod", "classmethod"):
            if prop in item.get("properties", []):
                yield f":{prop}:"
        if item.get("return_annotation"):
            yield f":type: {self.format_annotation(item['return_annotation'])}"
        yield ""

        yield from self.render_info(item=item, symbol=symbol, **kwargs)

        yield "````"
        yield ""

    def render_method(
        self, item: ItemData, symbol: Symbol | None, **kwargs
    ) -> t.Iterable[str]:
        """Create the content for a method."""
        short_name = item["full_name"].split(".")[-1]
        show_annotations = self.show_annotations(item)
        sig = f"{short_name}({self.format_args(item['args'], show_annotations, ignore_self='self')})"
        if show_annotations and item.get("return_annotation"):
            sig += f" -> {self.format_annotation(item['return_annotation'])}"

        yield f"````{{py:method}} {sig}"
        yield f":canonical: {item['full_name']}"
        if self.no_index(item):
            yield ":noindex:"
        # TODO overloads
        # TODO collect final decorated in analysis
        for prop in (
            "abstractmethod",
            "async",
            "classmethod",
            "final",
            "staticmethod",
        ):
            if prop in item.get("properties", []):
                yield f":{prop}:"

        yield from self.render_info(item=item, symbol=symbol, **kwargs)

        yield "````"
        yield ""

    def render_attribute(
        self, item: ItemData, symbol: Symbol, **kwargs
    ) -> t.Iterable[str]:
        """Create the content for an attribute."""
        yield from self.render_data(item, symbol, **kwargs)

    def render_data(
        self, item: ItemData, symbol: Symbol, **kwargs
    ) -> t.Iterable[str]:
        """Create the content for a data item."""
        short_name = item["full_name"].split(".")[-1]

        yield f"````{{py:{item['type']}}} {short_name}"
        yield f":canonical: {item['full_name']}"
        if self.no_index(item):
            yield ":noindex:"
        for prop in ("abstractmethod", "classmethod"):
            if prop in item.get("properties", []):
                yield f":{prop}:"
        if item.get("annotation"):
            yield f":type: {self.format_annotation(item['annotation'])}"

        # only get value if symbol has a parent (e.g. TypeVar does not)
        if parent := kwargs.get("parent"):
            if (value := parent.get_attr_value(short_name)) is not None:
                yield f"   {value}"

        yield ""

        yield from self.render_info(item=item, symbol=symbol, **kwargs)

        yield "````"
        yield ""

    def render_inherited(self, item: ItemData, parent: Symbol = None, **kwargs):
        lines = []

        # astroid shows collections.abc as _collections_abc, so get
        # "inherited from" manually from the class itself
        if item.get("inherited", None):
            short_name = item["full_name"].split(".")[-1]

            ancestor = parent.get_ancestor(short_name)

            if symbol := self.symbol_map.lookup(ancestor):
                ancestor = symbol.canonical.virt_path

            if ancestor.startswith("builtins."):
                ancestor = ancestor[len("builtins") :]

            inherited = f"{{obj}}`{ancestor}`"

            lines += [f"*Inherited from:* {inherited}"]

        return lines

    def render_docstring(
        self, item: ItemData, summary=False, allow_titles=False
    ):
        lines = []

        col_prefix = "  - " if summary else ""
        indent = "    " if summary else ""

        if self.show_docstring(item):
            lines += [
                f"{col_prefix}```{{autodoc2-docstring}} {item['full_name']}"
            ]

            if parser_name := self.get_doc_parser(item["full_name"]):
                lines += [f"{indent}:parser: {parser_name}"]

            if allow_titles:
                lines += [f"{indent}:allowtitles:"]

            if summary:
                lines += [f"{indent}:summary:"]

            lines += [f"{indent}```"]
        else:
            lines += [f"{col_prefix}"]

        lines += [""]

        return lines

    def render_init(self, item: ItemData):
        """Render initializer for classes"""

        lines = []

        init_item = self.get_item(f"{item['full_name']}.__init__")
        if init_item and self.show_docstring(init_item):
            doc_lines = [line.strip() for line in init_item["doc"].split("\n")]

            # check if there's a description besides just params
            has_desc = any(
                [line != "" and not line.startswith(":") for line in doc_lines]
            )

            if has_desc:
                lines += [
                    "```{rubric} Initialization:",
                    "```",
                    "",
                ]

            lines += self.render_docstring(init_item)

        return lines

    def get_bases(self, item: ItemData) -> list[str]:
        bases = []

        for base in item.get("bases", []):
            # remove generics, don't want to expose those for now
            base = base.split("[")[0]

            bases.append(self.symbol_map.resolve(base))

        return bases

    def render_bases(self, item: ItemData):
        lines = []
        bases = self.get_bases(item)

        if bases and self.show_class_inheritance(item):
            lines += [
                "```{rubric} Bases:",
                "```",
            ]

            lines += self.render_list([f"{{py:obj}}`{base}`" for base in bases])

        return lines

    def render_info(
        self, item: ItemData = None, symbol: Symbol = None, **kwargs
    ):
        lines = []
        lines += self.render_aliases(symbol)
        lines += self.render_inherited(item, **kwargs)
        lines += self.render_docstring(item)
        return lines

    def render_aliases(self, symbol: Symbol):
        lines = []
        if symbol and len(symbol.aliases):
            lines += [
                "```{rubric} Aliases:",
                "```",
            ]

            lines += self.render_list(
                [f"`{sym.virt_path}`" for sym in symbol.aliases]
            )

        return lines

    def render_list(self, strings: list[str]):
        lines = []

        # all but last need to end in \
        if len(strings) > 1:
            lines += [f"{s}\\" for s in strings[:-1]]

        # last one doesn't
        lines += [strings[-1]]

        return lines

    def _reformat_cls_base_myst(self, value: str) -> str:
        """Reformat the base of a class for RST.

        Base annotations can come in the form::

            A[B, C, D]

        which we want to reformat as::

            {py:obj}`A`\\[{py:obj}`B`, {py:obj}`C`, {py:obj}`D`\\]

        """
        result = ""
        for sub_target in _RE_DELIMS.split(value.strip()):
            sub_target = sub_target.strip()
            if _RE_DELIMS.match(sub_target):
                result += f"{sub_target}"
                if sub_target.endswith(","):
                    result += " "
                else:
                    result += "\\"
            elif sub_target:
                if result.endswith("\\"):
                    result = result[:-1]
                result += f"{{py:obj}}`{self.format_base(sub_target)}`\\"

        if result.endswith("\\"):
            result = result[:-1]

        return result
